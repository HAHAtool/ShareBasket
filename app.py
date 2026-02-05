import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv
import hashlib
import secrets
import base64

# 1. 初始化設定
st.set_page_config(page_title="分食趣", page_icon="🛒")

# 確保每一位使用者有獨立的 Client
if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(
        st.secrets["SUPABASE_URL"], 
        st.secrets["SUPABASE_KEY"]
    )

supabase: Client = st.session_state.supabase

# --- 2. 手動 PKCE 工具函式 ---
def generate_pkce_pair():
    # 產生 code_verifier
    verifier = secrets.token_urlsafe(64)
    # 產生 code_challenge (SHA256 雜湊後進行 Base64 編碼)
    sha256 = hashlib.sha256(verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').replace('=', '')
    return verifier, challenge

# --- 3. 處理 OAuth 回傳 ---
params = st.query_params
if "code" in params:
    auth_code = params["code"]
    # 從 session_state 找回剛才存下來的 verifier
    code_verifier = st.session_state.get("pkce_verifier")
    
    if auth_code and code_verifier:
        try:
            # 關鍵：帶入 code 和當初產生的 verifier 進行交換
            res = supabase.auth.exchange_code_for_session({
                "auth_code": auth_code,
                "code_verifier": code_verifier
            })
            st.session_state.user = res.user
            # 成功後清理，避免重複觸發
            st.query_params.clear()
            if "pkce_verifier" in st.session_state:
                del st.session_state["pkce_verifier"]
            st.rerun()
        except Exception as e:
            st.error(f"⚠️ 驗證失敗: {e}")
            st.query_params.clear()
    else:
        st.error("❌ 找不到驗證密鑰 (Verifier)，請嘗試重新登入。")
        st.query_params.clear()

# --- 4. 登入/登出邏輯 ---
def handle_login():
    # 1. 自己產生 PKCE 密鑰
    verifier, challenge = generate_pkce_pair()
    # 2. 存在 session_state 裡，等跳轉回來用
    st.session_state["pkce_verifier"] = verifier
    
    # 3. 發起 OAuth 並帶入 challenge
    res = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": st.secrets["REDIRECT_URI"],
            "query_params": {"prompt": "select_account"},
            "code_challenge": challenge,
            "code_challenge_method": "s256"
        }
    })
    if res.url:
        st.link_button("🚀 確認前往 Google 登入", res.url)

# --- 5. UI 介面 ---
user = None
try:
    session_res = supabase.auth.get_session()
    if session_res and session_res.session:
        user = session_res.session.user
except:
    user = None

st.title("🛒 分食趣")

with st.sidebar:
    st.header("👤 會員中心")
    if user:
        st.success(f"已登入: {user.email}")
        if st.button("登出"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        st.info("請先登入")
        handle_login()

if user:
    st.write("### 🎉 登入成功！")
    st.write("你現在可以正常使用分食功能了。")

# --- 5. 主畫面標題與 Tab ---
st.title("🛒 分食趣-現場媒合")
tab1, tab2 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團"])

with tab1:
    try:
        res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").order("created_at", desc=True).execute()
        items = res.data
        if not items:
            st.info("目前現場沒有人發起分食。")
        else:
            for item in items:
                with st.container(border=True):
                    col_info, col_btn = st.columns([3, 1])
                    with col_info:
                        st.subheader(item['item_name'])
                        st.write(f"📍 {item['stores']['branch_name']} | 👤 主揪：{item['creator_nickname']}")
                        st.write(f"💵 單價：**${int(item['unit_price'])}** / 份")
                    with col_btn:
                        st.metric("剩餘", f"{item['remaining_units']} 份")
                        if st.button(f"我要 +1", key=f"join_{item['id']}"):
                            if not user:
                                st.error("請先登入才能加入！")
                            else:
                                new_remain = item['remaining_units'] - 1
                                status = 'active' if new_remain > 0 else 'closed'
                                supabase.table("groups").update({"remaining_units": new_remain, "status": status}).eq("id", item['id']).execute()
                                st.success(f"✅ 成功加入！請與 {item['creator_nickname']} 聯繫。")
                                st.balloons()
                                st.rerun()
    except Exception as e:
        st.error(f"讀取失敗: {e}")

with tab2:
    if not user:
        st.warning("🛑 請先登入 Google 帳號。")
    else:
        if not st.session_state.confirm_publish:
            st.subheader("📢 第一步：填寫內容")
            stores_res = supabase.table("stores").select("*").execute().data
            store_map = {s['branch_name']: s['id'] for s in stores_res}
            selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
            
            pops = supabase.table("popular_items").select("*").execute().data
            item_name = st.selectbox("商品名稱", [p['name'] for p in pops])
            
            price = st.number_input("商品總價格", min_value=1, value=259)
            total_u = st.number_input("商品總包裝入數", min_value=1, value=12)
            
            col_my, col_others = st.columns(2)
            with col_my:
                my_stay = st.number_input("主揪自留數量", min_value=1, max_value=total_u, value=1)
            with col_others:
                others_get = total_u - my_stay
                st.metric("求分走數量", f"{others_get} 份")
            
            u_price = math.ceil(price / total_u)
            if st.button("📝 檢查發布內容", use_container_width=True):
                st.session_state.temp_post = {
                    "item": item_name, "price": price, "u_price": u_price,
                    "others": others_get, "my_stay": my_stay, "store_id": store_map[selected_store]
                }
                st.session_state.confirm_publish = True
                st.rerun()
        else:
            post = st.session_state.temp_post
            st.subheader("📢 第二步：確認發布")
            st.warning(f"確認：{post['item']} ${post['price']}，您留 {post['my_stay']} 份，求分 {post['others']} 份？")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("❌ 修改內容"):
                    st.session_state.confirm_publish = False
                    st.rerun()
            with c2:
                if st.button("✅ 正式發布", type="primary"):
                    new_data = {
                        "creator_id": user.id,
                        "creator_nickname": user.email.split('@')[0],
                        "store_id": post['store_id'],
                        "item_name": post['item'],
                        "total_price": post['price'],
                        "total_units": post['my_stay'] + post['others'],
                        "unit_price": post['u_price'],
                        "remaining_units": post['others'],
                        "creator_stay_units": post['my_stay']
                    }
                    supabase.table("groups").insert(new_data).execute()
                    # 指定成功訊息格式
                    st.success(f"🎉 {post['item']} ${post['price']} 求分 {post['others']} 顆發布成功！")
                    st.balloons()
                    st.session_state.confirm_publish = False
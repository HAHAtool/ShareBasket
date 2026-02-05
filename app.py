import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv
import hashlib
import secrets
import base64

# --- 1. 初始化 Supabase ---
url = st.secrets["SUPABASE_URL"]
key = st.secrets["SUPABASE_KEY"]

if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(url, key)
supabase = st.session_state.supabase

# --- 2. PKCE 標準工具函式 ---
def generate_pkce():
    """生成符合 RFC 7636 規範的 PKCE 密鑰對"""
    # Verifier: 隨機安全字串
    verifier = secrets.token_urlsafe(64)
    # Challenge: SHA256 雜湊後的 Base64 編碼
    sha256 = hashlib.sha256(verifier.encode('utf-8')).digest()
    challenge = base64.urlsafe_b64encode(sha256).decode('utf-8').replace('=', '')
    return verifier, challenge

# --- 3. 處理從 Google 跳轉回來的 Callback ---
q_params = st.query_params
if "code" in q_params:
    auth_code = q_params["code"]
    # 從 session_state 找回跳轉前存下來的 verifier
    stored_verifier = st.session_state.get("code_verifier")
    
    if auth_code and stored_verifier:
        try:
            # 依照官方標準交換 Session
            res = supabase.auth.exchange_code_for_session({
                "auth_code": auth_code, 
                "code_verifier": stored_verifier
            })
            if res.user:
                st.session_state.user = res.user
                # 成功後清理
                st.query_params.clear()
                if "code_verifier" in st.session_state:
                    del st.session_state["code_verifier"]
                st.rerun()
        except Exception as e:
            st.error(f"❌ 安全驗證交換失敗: {e}")
            st.query_params.clear()

# --- 4. 取得使用者狀態 ---
# 優先檢查 SDK 的 session，若無則看我們手動存的
user = None
try:
    session_data = supabase.auth.get_session()
    user = session_data.user if session_data else st.session_state.get("user")
except:
    user = st.session_state.get("user")

# --- 5. UI 介面 ---
st.title("🛒 分食趣")

with st.sidebar:
    st.header("👤 會員中心")
    if user:
        st.success(f"✅ 已安全登入: {user.email}")
        if st.button("登出系統"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        st.info("請使用 Google 帳號登入")
        
        # 發起登入流程
        if st.button("🚀 使用 Google 一鍵登入"):
            # A. 生成 PKCE 密鑰
            v, c = generate_pkce()
            # B. 將 verifier 存入 session，這樣跳轉回來才找得到
            st.session_state["code_verifier"] = v
            
            # C. 請求登入連結，並傳入 challenge
            res = supabase.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": st.secrets["REDIRECT_URI"],
                    "query_params": {"prompt": "select_account"},
                    "code_challenge": c,
                    "code_challenge_method": "s256"
                }
            })
            
            if res.url:
                # D. 提供安全連結
                st.link_button("確認前往 Google 驗證", res.url)

# --- 6. 成功後的畫面 ---
if user:
    st.balloons()
    st.write(f"### 認證成功！歡迎回來，{user.email}")
else:
    st.write("---")
    st.info("👋 歡迎！請先完成登入。")
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
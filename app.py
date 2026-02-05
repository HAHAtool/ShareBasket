import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv

# 1. 初始化與環境設定
load_dotenv()
url = st.secrets.get("SUPABASE_URL")
key = st.secrets.get("SUPABASE_KEY")
supabase: Client = create_client(url, key)

st.set_page_config(page_title="分食趣", page_icon="🛒", layout="centered")

# --- 2. 函式定義區 (確保在呼叫前定義) ---

def get_user():
    """獲取目前登入的使用者"""
    try:
        # 檢查當前的 Session
        session_res = supabase.auth.get_session()
        if session_res and session_res.session:
            return session_res.session.user
        
        user_res = supabase.auth.get_user()
        return user_res.user if user_res else None
    except Exception:
        return None

def login_with_google():
    """發起 Google OAuth 登入"""
    target_url = "https://cdhbz3unr3cpvmwnvjpyjr.streamlit.app"
    try:
        auth_res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {"redirect_to": target_url}
        })
        return auth_res.url if auth_res else None
    except Exception as e:
        st.error(f"❌ 登入初始化失敗: {str(e)}")
        return None

# --- 3. 處理登入邏輯與 Session ---

# 偵測 OAuth 回傳
if "code" in st.query_params:
    temp_user = get_user()
    if temp_user:
        st.query_params.clear()
        st.rerun()
    else:
        # 如果網址有 code 但還沒拿到 user，顯示手動重整按鈕解決延遲
        st.info("驗證中，若畫面未跳轉請點擊下方按鈕")
        if st.button("確認完成登入"):
            st.rerun()

# 初始化發布狀態
if "confirm_publish" not in st.session_state:
    st.session_state.confirm_publish = False

user = get_user()

# --- 4. 側邊欄：使用者資訊 ---
with st.sidebar:
    st.title("👤 會員中心")
    if user:
        nickname = user.email.split('@')[0]
        st.success(f"✅ 已登入：{nickname}")
        if st.button("登出系統"):
            supabase.auth.sign_out()
            st.rerun()
    else:
        st.warning("請先登入以發布揪團")
        auth_url = login_with_google()
        if auth_url:
            st.markdown(f'''
                <a href="{auth_url}" target="_self" style="text-decoration: none;">
                    <button style="width: 100%; background-color: #4285F4; color: white; padding: 12px; border: none; border-radius: 5px; cursor: pointer; font-weight: bold;">
                        🚀 使用 Google 一鍵登入
                    </button>
                </a>
            ''', unsafe_allow_html=True)

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
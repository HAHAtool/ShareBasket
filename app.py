import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv

# --- 1. 初始化 Supabase 用戶端 ---
@st.cache_resource
def init_connection():
    url = st.secrets["SUPABASE_URL"]
    key = st.secrets["SUPABASE_KEY"]
    return create_client(url, key)

supabase: Client = init_connection()

# --- 2. 身分驗證處理邏輯 ---
def handle_auth():
    # A. 檢查網址是否有 OAuth 回傳的 code
    if "code" in st.query_params:
        auth_code = st.query_params.get("code")
        try:
            # 關鍵步驟：用 Code 換取 Session
            res = supabase.auth.exchange_code_for_session({"auth_code": auth_code})
            st.session_state.user = res.user
            # 清除網址參數，避免重複觸發
            st.query_params.clear()
            st.rerun()
        except Exception as e:
            st.error(f"驗證失敗：{e}")

    # B. 如果 session_state 沒有 user，嘗試從 Supabase 客戶端獲取目前 session
    if "user" not in st.session_state or st.session_state.user is None:
        try:
            session = supabase.auth.get_session()
            if session:
                st.session_state.user = session.user
            else:
                st.session_state.user = None
        except:
            st.session_state.user = None

def login():
    # 發起 Google 登入，redirect_to 必須完全符合 Supabase 設定
    res = supabase.auth.sign_in_with_oauth({
        "provider": "google",
        "options": {
            "redirect_to": st.secrets["REDIRECT_URI"]
        }
    })
    if res.url:
        # 在 Streamlit 中，使用 markdown 建立一個直接在原視窗開啟的連結最穩定
        st.markdown(f'<a href="{res.url}" target="_self">點擊前往 Google 登入</a>', unsafe_allow_html=True)

def logout():
    supabase.auth.sign_out()
    st.session_state.user = None
    st.rerun()

# 執行驗證邏輯
handle_auth()

# --- 3. UI 介面 ---
st.title("🛒 分食趣 - 現場媒合")

with st.sidebar:
    st.header("👤 會員中心")
    
    if st.session_state.user:
        user = st.session_state.user
        st.success(f"已登入：{user.email}")
        if st.button("登出"):
            logout()
    else:
        st.warning("您尚未登入")
        if st.button("使用 Google 登入"):
            login()

# 主畫面內容
if st.session_state.user:
    st.write("🎉 歡迎回來！現在你可以發起或加入分食。")
    # 這裡放你後續的表單或清單
else:
    st.info("請先從左側邊欄登入以查看更多功能。")

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
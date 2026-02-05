import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv

# 1. 頁面基本設定（必須在最上方）
st.set_page_config(page_title="分食趣", page_icon="🛒")

# 2. 核心：建立一個絕對獨立的 Supabase Client
def get_clean_client():
    # 這裡不使用任何 cache，確保每個使用者進來都是全新的
    return create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])

# 初始化屬於這個 Session 的 Client
if "supabase" not in st.session_state:
    st.session_state.supabase = get_clean_client()

supabase: Client = st.session_state.supabase

# 3. 核心：處理驗證代碼交換 (Auth Exchange)
def handle_auth_flow():
    # 抓取網址參數
    params = st.query_params
    
    if "code" in params:
        auth_code = params["code"]
        try:
            # 執行交換
            res = supabase.auth.exchange_code_for_session({"auth_code": auth_code})
            # 將 user 存入 session_state
            st.session_state.user = res.user
            # 關鍵：成功後立刻清除網址參數，防止二次執行觸發 403
            st.query_params.clear()
            # 強制刷新頁面，回到沒有 code 的乾淨狀態
            st.rerun()
        except Exception as e:
            # 如果是重複觸發，這裡會攔截到，我們直接清空參數就好
            st.query_params.clear()
            st.rerun()

# 4. 執行驗證與狀態更新
handle_auth_flow()

# 檢查目前 Supabase Client 裡真正的登入狀態
try:
    current_session = supabase.auth.get_session()
    user = current_session.user if current_session else None
except:
    user = None

# 5. UI 介面區
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
        st.info("尚未登入")
        if st.button("🚀 使用 Google 登入"):
            # 發起登入
            res = supabase.auth.sign_in_with_oauth({
                "provider": "google",
                "options": {
                    "redirect_to": st.secrets["REDIRECT_URI"],
                    "query_params": {"prompt": "select_account"}
                }
            })
            if res.url:
                # 使用最直接的連結跳轉
                st.markdown(f'''
                    <meta http-equiv="refresh" content="0; url={res.url}">
                    <a href="{res.url}">如果沒有自動跳轉，請點擊這裡</a>
                ''', unsafe_allow_html=True)

# 6. 主畫面邏輯
if user:
    st.write(f"### 歡迎，{user.email.split('@')[0]}！")
    st.info("現在你可以看到分食清單與發起功能。")
    # 這裡放你的 Table 與 Form...
else:
    st.warning("請先完成登入，以查看現場分食資訊。")

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
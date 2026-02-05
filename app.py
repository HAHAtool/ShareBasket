import streamlit as st
from supabase import create_client, Client
import os
import math
from dotenv import load_dotenv

# 1. 初始化
load_dotenv()
url = st.secrets.get("SUPABASE_URL") or os.getenv("SUPABASE_URL")
key = st.secrets.get("SUPABASE_KEY") or os.getenv("SUPABASE_KEY")
supabase: Client = create_client(url, key)

st.set_page_config(page_title="分食趣", page_icon="🛒", layout="centered")

# --- 2. 處理 Google 登入邏輯 (強制修正版) ---
def get_user():
    """獲取目前登入的使用者"""
    try:
        # 在 Streamlit 中，這會檢查當前的 auth session
        user_data = supabase.auth.get_user()
        if user_data and user_data.user:
            return user_data.user
        return None
    except Exception:
        return None

# --- 3. 核心修正：手動處理網址回傳的 code ---
# 如果網址有 code 參數，代表 Google 剛跳轉回來
if "code" in st.query_params:
    # 嘗試獲取使用者資訊以完成 code 與 session 的交換
    current_user = get_user()
    
    # 無論是否抓到 user，只要網址有 code 就執行一次清理並重整
    # 這能解決網址代碼過期導致的 403 或驗證失敗
    if st.button("🚀 驗證完成，點擊進入系統"):
        st.query_params.clear() 
        st.rerun()

user = get_user()

# --- 側邊欄顯示 ---
with st.sidebar:
    st.title("👤 會員中心")
    if user:
        nickname = user.email.split('@')[0]
        st.success(f"✅ 歡迎回來：{nickname}")
        if st.button("登出系統"):
            supabase.auth.sign_out()
            st.rerun()
    else:
        st.warning("請先登入以發布揪團")
        # 這裡直接生成 Google 登入網址
        auth_url = login_with_google()
        if auth_url:
            st.markdown(f'''
                <a href="{auth_url}" target="_self" style="text-decoration: none;">
                    <button style="
                        width: 100%;
                        background-color: #4285F4;
                        color: white;
                        padding: 12px;
                        border: none;
                        border-radius: 5px;
                        cursor: pointer;
                        font-weight: bold;">
                        Google 一鍵登入
                    </button>
                </a>
            ''', unsafe_allow_html=True)


# --- 主畫面標題 ---
st.title("🛒 分食趣-現場媒合")

tab1, tab2 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團"])

# --- Tab 1: 顯示清單 ---
with tab1:
    try:
        # 增加會員判斷：只有登入者能看到誰發布的
        res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").order("created_at", desc=True).execute()
        items = res.data
        if not items:
            st.info("目前現場沒有人在揪喔，快去發起一個！")
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
                                st.error("請先登入才能加入分食！")
                            else:
                                new_remain = item['remaining_units'] - 1
                                status = 'active' if new_remain > 0 else 'closed'
                                supabase.table("groups").update({"remaining_units": new_remain, "status": status}).eq("id", item['id']).execute()
                                st.success(f"✅ 成功加入！請與 {item['creator_nickname']} 聯繫。")
                                st.balloons()
                                st.rerun()
    except Exception as e:
        st.error(f"讀取資料失敗: {e}")

# --- Tab 2: 發起揪團 (兩段式確認) ---
with tab2:
    if not user:
        st.warning("🛑 請先使用 Google 登入後再發起揪團。")
    else:
        if not st.session_state.confirm_publish:
            st.subheader("第一步：填寫內容")
            
            # 抓取資料庫商店與商品
            stores_res = supabase.table("stores").select("*").execute().data
            store_map = {s['branch_name']: s['id'] for s in stores_res}
            selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
            
            pops = supabase.table("popular_items").select("*").execute().data
            pop_names = [p['name'] for p in pops]
            item_name = st.selectbox("商品名稱", pop_names)
            
            total_price = st.number_input("商品總價格", min_value=1, value=259)
            total_u = st.number_input("商品總包裝入數", min_value=1, value=12)
            
            # 數量分配優化：主揪自留與求分
            col_my, col_others = st.columns(2)
            with col_my:
                my_stay = st.number_input("主揪自留數量", min_value=1, max_value=total_u, value=1)
            with col_others:
                others_get = total_u - my_stay
                st.metric("求分走數量", f"{others_get} 份")
            
            u_price = math.ceil(total_price / total_u)
            st.info(f"💡 系統計算單價：${u_price} / 份")

            if st.button("📝 檢查發布內容", use_container_width=True):
                # 儲存暫存資料到 session_state 供下一步使用
                st.session_state.temp_post = {
                    "item": item_name, "price": total_price, "u_price": u_price,
                    "others": others_get, "my_stay": my_stay, "store_id": store_map[selected_store]
                }
                st.session_state.confirm_publish = True
                st.rerun()
        
        else:
            # 第二步：二次確認
            post = st.session_state.temp_post
            st.subheader("第二步：確認並發布")
            st.warning(f"請確認：{post['item']} ${post['price']}，您自留 {post['my_stay']} 份，求分 {post['others']} 份？")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("❌ 修改內容", use_container_width=True):
                    st.session_state.confirm_publish = False
                    st.rerun()
            with c2:
                if st.button("✅ 確認正式發布", type="primary", use_container_width=True):
                    # 寫入資料庫，帶入 user.id 辨認身分
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
                    
                    # 顯示指定的成功訊息格式
                    st.success(f"🎉 {post['item']} ${post['price']} 求分 {post['others']} 顆發布成功！")
                    st.balloons()
                    
                    st.session_state.confirm_publish = False
                    # 這裡不自動 rerun，讓使用者看清楚成功訊息
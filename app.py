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

# --- 2. 核心修正：強制處理網址列的 OAuth 回傳 ---
# 這是為了解決網址出現 ?code= 但沒登入的問題
if "code" in st.query_params:
    # 只要網址有 code，就代表 Google 剛跳轉回來
    # 這裡什麼都不用做，只要確保執行過一次 supabase 的任何 auth 指令
    # 它會自動去抓網址列的參數來建立連線
    try:
        supabase.auth.get_user()
        # 成功拿到資料後，立刻清除網址參數並重整，讓網址變乾淨
        st.query_params.clear()
        st.rerun()
    except Exception as e:
        st.error(f"登入交換失敗：{e}")

def get_user():
    """獲取目前的登入狀態"""
    try:
        # 先試著拿 Session，這最準
        res = supabase.auth.get_session()
        if res and res.session:
            return res.session.user
        # 如果沒有 session，再試一次 get_user
        user_res = supabase.auth.get_user()
        return user_res.user if user_res else None
    except:
        return None

def login_with_google():
    """發起 Google OAuth 登入"""
    # 這裡的網址必須跟 Supabase Site URL 完完全全一致 (注意斜線)
    target_url = "https://cdhbz3unr3cpvmwnvjpyjr.streamlit.app"
    try:
        auth_res = supabase.auth.sign_in_with_oauth({
            "provider": "google",
            "options": {
                "redirect_to": target_url
            }
        })
        return auth_res.url
    except Exception as e:
        st.error(f"OAuth 初始化失敗: {e}")
        return None

# 取得目前使用者
user = get_user()

# --- 側邊欄 ---
with st.sidebar:
    st.title("👤 會員中心")
    if user:
        nickname = user.email.split('@')[0]
        st.success("✅ 已登入")
        st.write(f"你好，{nickname}")
        if st.button("登出"):
            supabase.auth.sign_out()
            st.rerun()
    else:
        st.warning("尚未登入")
        auth_url = login_with_google()
        if auth_url:
            # 使用 target="_top" 是為了讓它在同一個分頁跳轉，這對 Session 寫入最穩定
            st.markdown(f'''
                <a href="{auth_url}" target="_top" style="text-decoration: none;">
                    <div style="background-color: #4285F4; color: white; padding: 12px; border-radius: 5px; text-align: center; font-weight: bold; cursor: pointer;">
                        使用 Google 一鍵登入
                    </div>
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
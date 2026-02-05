import streamlit as st
from supabase import create_client, Client
import math

# 1. 基礎連線與初始化
if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(
        st.secrets["SUPABASE_URL"], 
        st.secrets["SUPABASE_KEY"]
    )
supabase = st.session_state.supabase

# 初始化 Session State 變數
if "confirm_publish" not in st.session_state:
    st.session_state.confirm_publish = False
if "temp_post" not in st.session_state:
    st.session_state.temp_post = None

# --- 2. 認證邏輯：獲取使用者 ---
def get_user():
    try:
        # 獲取當前 Session
        res = supabase.auth.get_session()
        if res and res.session:
            return res.user
        return None
    except:
        return None

user = get_user()

# --- 3. UI 介面：側邊欄登入/註冊 ---
st.title("🛒 分食趣")

with st.sidebar:
    st.header("👤 會員中心")
    if user:
        st.success(f"✅ 已登入: {user.email}")
        st.caption("登入效期：12 小時 (請至後台設定)")
        if st.button("登出"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        auth_mode = st.radio("模式", ["登入", "註冊"], horizontal=True)
        email = st.text_input("Email")
        password = st.text_input("密碼", type="password")
        
        if auth_mode == "登入":
            if st.button("確認登入", use_container_width=True):
                try:
                    res = supabase.auth.sign_in_with_password({"email": email, "password": password})
                    if res.user:
                        st.success("登入成功！")
                        st.rerun()
                except Exception as e:
                    st.error(f"❌ 登入失敗: {str(e)}")
        else:
            if st.button("立即註冊", use_container_width=True):
                try:
                    # 註冊後預設會發送驗證信，除非你在 Supabase 關閉驗證
                    res = supabase.auth.sign_up({"email": email, "password": password})
                    st.info("註冊成功！請檢查信箱驗證（或直接嘗試登入，視後台設定而定）。")
                except Exception as e:
                    st.error(f"❌ 註冊失敗: {str(e)}")

# --- 4. 主畫面：分食功能 ---
st.markdown("---")
tab1, tab2 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團"])

with tab1:
    try:
        # 讀取進行中的媒合
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
                                st.error("🛑 請先登入才能加入！")
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
        st.warning("🛑 發起分食前，請先於側邊欄完成會員登入。")
    else:
        if not st.session_state.confirm_publish:
            st.subheader("📢 第一步：填寫內容")
            # 獲取分店與熱門商品
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
            st.warning(f"確認：{post['item']} 總價 ${post['price']}，您留 {post['my_stay']} 份，求分 {post['others']} 份？")
            
            c1, c2 = st.columns(2)
            with c1:
                if st.button("❌ 修改內容", use_container_width=True):
                    st.session_state.confirm_publish = False
                    st.rerun()
            with c2:
                if st.button("✅ 正式發布", type="primary", use_container_width=True):
                    new_data = {
                        "creator_id": user.id,
                        "creator_nickname": user.email.split('@')[0],
                        "store_id": post['store_id'],
                        "item_name": post['item'],
                        "total_price": post['price'],
                        "total_units": post['my_stay'] + post['others'],
                        "unit_price": post['u_price'],
                        "remaining_units": post['others'],
                        "creator_stay_units": post['my_stay'],
                        "status": "active"
                    }
                    supabase.table("groups").insert(new_data).execute()
                    st.success(f"🎉 {post['item']} 發布成功！剩餘 {post['others']} 份等待領取。")
                    st.balloons()
                    st.session_state.confirm_publish = False
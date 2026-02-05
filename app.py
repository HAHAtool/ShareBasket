import streamlit as st
from supabase import create_client
import math

# 1. 基礎連線
if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = st.session_state.supabase

# 初始化狀態
if "confirm_publish" not in st.session_state: st.session_state.confirm_publish = False
if "temp_post" not in st.session_state: st.session_state.temp_post = None

# --- 2. 認證與 Profiles 邏輯 ---
def get_user():
    if "user_obj" in st.session_state: return st.session_state.user_obj
    try:
        res = supabase.auth.get_session()
        if res and res.session:
            st.session_state.user_obj = res.user
            return res.user
    except: pass
    return None

def get_nickname(uid):
    try:
        res = supabase.table("profiles").select("nickname").eq("id", uid).maybe_single().execute()
        return res.data['nickname'] if res.data else "神秘分食友"
    except: return "未知用戶"

user = get_user()

# --- 3. 側邊欄與導覽 ---
with st.sidebar:
    st.header("👤 會員選單")
    if user:
        # 顯示暱稱而非 Email
        my_nick = get_nickname(user.id)
        st.success(f"你好，{my_nick}！")
        
        # 檢查有無新通知 (有人跟團)
        notif = supabase.table("groups").select("id").eq("creator_id", user.id).eq("has_new_join", True).execute()
        if notif.data:
            st.warning(f"🔔 有 {len(notif.data)} 個揪團有新進展！")
            
        menu = st.radio("前往頁面", ["找分食/發起", "我的會員中心"])
        
        if st.button("登出"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        menu = "找分食/發起"
        auth_mode = st.radio("登入/註冊", ["登入", "註冊"])
        email = st.text_input("Email")
        pw = st.text_input("密碼", type="password")
        if st.button("確認"):
            try:
                if auth_mode == "登入":
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
                    if res.user: 
                        st.session_state.user_obj = res.user
                        st.rerun()
                else:
                    res = supabase.auth.sign_up({"email": email, "password": pw})
                    # 註冊後自動建立基本 Profile
                    if res.user:
                        supabase.table("profiles").insert({"id": res.user.id, "nickname": email.split('@')[0]}).execute()
                    st.info("註冊成功！請直接登入。")
            except Exception as e: st.error(f"錯誤: {e}")

# --- 4. 頁面邏輯：會員中心 ---
if user and menu == "我的會員中心":
    st.title("🛡️ 會員控制台")
    
    # 修改暱稱
    st.subheader("📝 修改公開顯示名稱")
    new_nick = st.text_input("新暱稱", placeholder=get_nickname(user.id))
    if st.button("儲存暱稱"):
        supabase.table("profiles").upsert({"id": user.id, "nickname": new_nick}).execute()
        st.success("暱稱已更新！")
        st.rerun()

    # 查看我的揪團
    m1, m2, m3 = st.tabs(["📢 我發起的", "🤝 我跟隨的", "⌛ 已結束"])
    
    with m1:
        my_groups = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "active").execute().data
        for g in my_groups:
            with st.container(border=True):
                c1, c2 = st.columns([3,1])
                c1.write(f"**{g['item_name']}** (剩餘 {g['remaining_units']} 份)")
                if g['has_new_join']: c1.info("🆕 有人加入了！")
                if c2.button("關閉/結束", key=f"close_{g['id']}"):
                    supabase.table("groups").update({"status": "closed", "has_new_join": False}).eq("id", g['id']).execute()
                    st.rerun()
                    
    with m2:
        # 查 group_members 表
        followed = supabase.table("group_members").select("*, groups(*)").eq("user_id", user.id).execute().data
        for f in followed:
            g = f['groups']
            if g['status'] == 'active':
                st.write(f"✅ 已跟團：{g['item_name']} (主揪：{g['creator_nickname']})")

    with m3:
        closed = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "closed").execute().data
        for c in closed:
            st.write(f"🌑 已結束：{c['item_name']} ({c['created_at'][:10]})")

# --- 5. 頁面邏輯：主頁面 ---
elif menu == "找分食/發起":
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
                                if not user: st.error("請先登入！")
                                elif user.id == item['creator_id']: st.warning("不能跟自己的團喔！")
                                else:
                                    new_remain = item['remaining_units'] - 1
                                    status = 'active' if new_remain > 0 else 'closed'
                                    # 更新主表，並標記 has_new_join 為 True (通知主揪)
                                    supabase.table("groups").update({
                                        "remaining_units": new_remain, 
                                        "status": status,
                                        "has_new_join": True 
                                    }).eq("id", item['id']).execute()
                                    # 寫入成員表
                                    supabase.table("group_members").insert({"group_id": item['id'], "user_id": user.id}).execute()
                                    st.success(f"✅ 成功加入！主揪已收到通知。")
                                    st.balloons()
                                    st.rerun()
        except Exception as e: st.error(f"讀取失敗: {e}")

    with tab2:
        if not user:
            st.warning("🛑 請先登入帳號。")
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
                with col_my: my_stay = st.number_input("主揪自留數量", min_value=1, max_value=total_u, value=1)
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
                            "creator_nickname": get_nickname(user.id), # 使用自訂暱稱
                            "store_id": post['store_id'],
                            "item_name": post['item'],
                            "total_price": post['price'],
                            "total_units": post['my_stay'] + post['others'],
                            "unit_price": post['u_price'],
                            "remaining_units": post['others'],
                            "self_units": post['my_stay'],
                            "status": "active"
                        }
                        supabase.table("groups").insert(new_data).execute()
                        st.success(f"🎉 發布成功！")
                        st.session_state.confirm_publish = False
                        st.rerun() # 解決問題 1：發完立即更新清單
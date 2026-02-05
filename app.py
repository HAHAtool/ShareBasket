import streamlit as st
from supabase import create_client
import math
from datetime import datetime

# --- 1. 基礎設定與連線 ---
st.set_page_config(page_title="分食趣-現場媒合", layout="wide")

if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = st.session_state.supabase

# 初始化 Session 狀態
for key in ["confirm_publish", "temp_post", "active_chat_id", "user_obj"]:
    if key not in st.session_state: st.session_state[key] = None if key != "confirm_publish" else False

# --- 2. 核心邏輯函數 ---

def get_user():
    if st.session_state.user_obj: return st.session_state.user_obj
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

# --- 3. 智慧通知與同步系統 (Fragment) ---

@st.fragment(run_every="8s")
def global_sync_v2(user_id):
    """背景同步：處理跟團提醒與新訊息提醒"""
    if not user_id: return
    try:
        # A. 跟團通知 (主揪視角)
        join_res = supabase.table("groups").select("id, item_name")\
            .eq("creator_id", user_id).eq("has_new_join", True).eq("status", "active").execute()
        
        for g in join_res.data:
            st.toast(f"🔔 有人加入「{g['item_name']}」！", icon="👤")
            if st.sidebar.button(f"不再提醒: {g['item_name']}", key=f"notif_j_{g['id']}"):
                supabase.table("groups").update({"has_new_join": False}).eq("id", g['id']).execute()
                st.rerun()

        # B. 新訊息通知 (主揪+成員)
        # 獲取身為主揪或成員的所有進行中團體
        my_groups = supabase.table("groups").select("id, item_name, last_chat_read_at").eq("creator_id", user_id).eq("status", "active").execute().data
        joined_res = supabase.table("group_members").select("group_id, last_chat_read_at, groups(item_name)").eq("user_id", user_id).execute().data
        
        all_active = []
        for g in my_groups: all_active.append({"id": g['id'], "name": g['item_name'], "read_at": g['last_chat_read_at']})
        for j in joined_res: 
            if j['groups']: all_active.append({"id": j['group_id'], "name": j['groups']['item_name'], "read_at": j['last_chat_read_at']})

        for group in all_active:
            latest = supabase.table("messages").select("created_at").eq("group_id", group['id']).order("created_at", desc=True).limit(1).execute().data
            if latest and latest[0]['created_at'] > group['read_at']:
                st.toast(f"💬 「{group['name']}」有新訊息！", icon="✉️")
    except: pass

@st.fragment(run_every="5s")
def render_chat_v2(group_id, user_id, is_creator):
    """即時聊天室：進入即更新已讀時間"""
    now_str = datetime.now().isoformat()
    if is_creator:
        supabase.table("groups").update({"last_chat_read_at": now_str}).eq("id", group_id).execute()
    else:
        supabase.table("group_members").update({"last_chat_read_at": now_str}).eq("group_id", group_id).eq("user_id", user_id).execute()

    st.markdown("---")
    msgs = supabase.table("messages").select("*").eq("group_id", group_id).order("created_at", desc=False).execute().data
    
    chat_box = st.container(height=300)
    with chat_box:
        if not msgs: st.caption("目前尚無對話")
        for m in msgs:
            is_me = str(m['user_id']) == str(user_id)
            with st.chat_message("user" if is_me else "assistant"):
                st.write(f"**{m['user_nickname']}**: {m['content']}")
                st.caption(f"{m['created_at'][11:16]}")
    
    if prompt := st.chat_input("說點什麼...", key=f"input_{group_id}"):
        supabase.table("messages").insert({
            "group_id": group_id, "user_id": user_id,
            "user_nickname": get_nickname(user_id), "content": prompt
        }).execute()
        st.rerun()

# --- 4. 側邊欄與頁面切換 ---
user = get_user()

with st.sidebar:
    st.title("👤 會員中心")
    if user:
        global_sync_v2(user.id)
        st.write(f"歡迎，**{get_nickname(user.id)}**")
        page = st.radio("功能選單", ["🔍 找分食清單", "📢 發起揪團", "🛡️ 會員控制台"])
        if st.button("登出"):
            supabase.auth.sign_out()
            st.session_state.clear()
            st.rerun()
    else:
        page = "🔍 找分食清單"
        auth_mode = st.radio("登入/註冊", ["登入", "註冊"])
        email = st.text_input("Email")
        pw = st.text_input("密碼", type="password")
        if st.button("執行"):
            try:
                if auth_mode == "登入":
                    res = supabase.auth.sign_in_with_password({"email": email, "password": pw})
                    if res.user: st.session_state.user_obj = res.user; st.rerun()
                else:
                    res = supabase.auth.sign_up({"email": email, "password": pw})
                    if res.user:
                        supabase.table("profiles").insert({"id": res.user.id, "nickname": email.split('@')[0]}).execute()
                        st.success("註冊成功，請登入")
            except Exception as e: st.error(str(e))

# --- 5. 頁面邏輯 ---

if page == "🔍 找分食清單":
    st.title("🛒 現場待領清單")
    if st.button("🔄 刷新清單"): st.rerun()
    
    items = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").order("created_at", desc=True).execute().data
    if not items:
        st.info("目前沒有人發起分食。")
    else:
        for item in items:
            with st.container(border=True):
                c1, c2 = st.columns([3, 1])
                with c1:
                    st.subheader(item['item_name'])
                    st.write(f"📍 {item['stores']['branch_name']} | 👤 主揪：{item['creator_nickname']}")
                    st.write(f"💵 金額：**${int(item['unit_price'])}** / 份")
                with c2:
                    if item['remaining_units'] > 0:
                        st.metric("剩餘", f"{item['remaining_units']} 份")
                        if st.button("我要 +1", key=f"j_{item['id']}"):
                            if not user: st.error("請先登入")
                            elif user.id == item['creator_id']: st.warning("不能跟自己的團")
                            else:
                                # 更新數量並重新開啟通知
                                supabase.table("groups").update({
                                    "remaining_units": item['remaining_units'] - 1,
                                    "has_new_join": True
                                }).eq("id", item['id']).execute()
                                supabase.table("group_members").insert({"group_id": item['id'], "user_id": user.id}).execute()
                                st.success("成功加入！請至控制台聯繫主揪。")
                                st.rerun()
                    else:
                        st.warning("🟠 已額滿 (面交中)")

elif page == "📢 發起揪團" and user:
    if not st.session_state.confirm_publish:
        st.title("📢 設定分食內容")
        stores = supabase.table("stores").select("*").execute().data
        store_map = {s['branch_name']: s['id'] for s in stores}
        selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
        pops = supabase.table("popular_items").select("*").execute().data
        item_name = st.selectbox("商品名稱", [p['name'] for p in pops])
        price = st.number_input("商品總價格", min_value=1, value=259)
        total_count = st.number_input("商品總個數", min_value=1, value=12)
        
        st.divider()
        col_a, col_b, col_c = st.columns(3)
        my_stay = col_a.number_input("主揪自留幾個？", min_value=1, value=2)
        left_for_others = total_count - my_stay
        col_b.metric("剩下個數", f"{left_for_others}")
        per_pack = col_c.number_input("幾份為一個？", min_value=1, value=2)
        
        others_parts = left_for_others // per_pack
        leftover = left_for_others % per_pack
        u_price = math.ceil(price / (total_count / per_pack))
        creator_pay = price - (others_parts * u_price)

        st.info(f"💡 結果：開放領取 **{others_parts}** 份，一份 **{per_pack}** 個。")
        if leftover > 0: st.warning(f"⚠️ {leftover} 顆歸主揪 (共 {my_stay + leftover} 顆)")
        st.success(f"💰 主揪應付：${int(creator_pay)} | 團員每份：${int(u_price)}")

        if st.button("📝 檢查並發布"):
            st.session_state.temp_post = {
                "item": item_name, "price": price, "u_price": u_price, "creator_pay": creator_pay,
                "others_parts": others_parts, "my_total": my_stay + leftover, 
                "store_id": store_map[selected_store], "total_count": total_count, "per_pack": per_pack
            }
            st.session_state.confirm_publish = True
            st.rerun()
    else:
        p = st.session_state.temp_post
        st.subheader("📢 最後確認")
        st.warning(f"{p['item']} | 團員付：${int(p['u_price'])} x {p['others_parts']} 份")
        if st.button("✅ 正式發布"):
            supabase.table("groups").insert({
                "creator_id": user.id, "creator_nickname": get_nickname(user.id),
                "store_id": p['store_id'], "item_name": p['item'], "total_price": p['price'],
                "total_units": p['total_count'], "unit_price": p['u_price'],     
                "remaining_units": p['others_parts'], "status": "active"
            }).execute()
            st.session_state.confirm_publish = False
            st.success("發布成功！")
            st.rerun()

elif page == "🛡️ 會員控制台" and user:
    st.title("🛡️ 我的控制台")
    t1, t2, t3 = st.tabs(["📢 我發起的", "🤝 我參加的", "⌛ 歷史記錄"])
    
    with t1:
        my_g = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "active").execute().data
        for g in my_g:
            with st.container(border=True):
                st.subheader(g['item_name'])
                c1, c2, c3 = st.columns(3)
                if c1.button("標記已讀", key=f"r_{g['id']}"):
                    supabase.table("groups").update({"has_new_join": False}).eq("id", g['id']).execute()
                    st.rerun()
                if c2.button("結案 (移入歷史)", key=f"cl_{g['id']}", type="primary"):
                    supabase.table("groups").update({"status": "closed"}).eq("id", g['id']).execute()
                    st.rerun()
                if c3.button("開啟/關閉聊天室", key=f"ct_{g['id']}"):
                    st.session_state.active_chat_id = g['id'] if st.session_state.active_chat_id != g['id'] else None
                
                if st.session_state.active_chat_id == g['id']:
                    render_chat_v2(g['id'], user.id, True)

    with t2:
        follows = supabase.table("group_members").select("*, groups(*)").eq("user_id", user.id).execute().data
        for f in [x for x in follows if x['groups']['status'] == 'active']:
            g = f['groups']
            with st.container(border=True):
                st.subheader(g['item_name'])
                st.write(f"主揪：{g['creator_nickname']} | 需付：${int(g['unit_price'])}")
                if st.button("聊天聯繫", key=f"ctj_{g['id']}"):
                    st.session_state.active_chat_id = g['id'] if st.session_state.active_chat_id != g['id'] else None
                if st.session_state.active_chat_id == g['id']:
                    render_chat_v2(g['id'], user.id, False)

    with t3:
        old = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "closed").execute().data
        for o in old: st.write(f"🌑 {o['item_name']} ({o['created_at'][:10]})")
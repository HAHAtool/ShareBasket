import streamlit as st
from supabase import create_client
import math

# --- 基礎設定 ---
if "supabase" not in st.session_state:
    st.session_state.supabase = create_client(st.secrets["SUPABASE_URL"], st.secrets["SUPABASE_KEY"])
supabase = st.session_state.supabase

# --- 認證邏輯 (保留你要求的雙重檢查) ---
def get_user():
    if "user_obj" in st.session_state: return st.session_state.user_obj
    try:
        res = supabase.auth.get_session()
        if res and res.session:
            st.session_state.user_obj = res.user
            return res.user
    except: pass
    return None

user = get_user()

# --- 主畫面導覽 ---
st.title("🛒 分食趣 - 精準分食版")
tab1, tab2, tab3 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團", "👤 會員中心"])

# --- Tab 1: 找分食清單 ---
with tab1:
    st.subheader("現場待領清單")
    if st.button("🔄 刷新即時清單"): st.rerun()

    res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").order("created_at", desc=True).execute()
    for item in (res.data or []):
        with st.container(border=True):
            col_info, col_btn = st.columns([3, 1])
            with col_info:
                st.subheader(item['item_name'])
                st.write(f"📍 {item['stores']['branch_name']} | 👤 主揪：{item['creator_nickname']}")
                st.write(f"💵 金額：**${int(item['unit_price'])}** / 份")
                
                # 金額提醒邏輯
                total_collected = item['unit_price'] * (item['remaining_units'] + item['self_units'])
                if total_collected > item['total_price']:
                    st.caption(f"⚠️ *本團金額經無條件進位，每份約多收 ${int(total_collected - item['total_price'])} 元作為雜費補貼")

            with col_btn:
                st.metric("剩餘", f"{item['remaining_units']} 份")
                if st.button("我要 +1", key=f"join_{item['id']}"):
                    if not user: st.error("請先登入！")
                    else:
                        new_remain = item['remaining_units'] - 1
                        status = 'active' if new_remain > 0 else 'closed'
                        supabase.table("groups").update({"remaining_units": new_remain, "status": status, "has_new_join": True}).eq("id", item['id']).execute()
                        supabase.table("group_members").insert({"group_id": item['id'], "user_id": user.id}).execute()
                        st.success("成功跟團！主揪已收到即時通知。")
                        st.rerun()

# --- Tab 2: 我要發起揪團 (核心邏輯修改) ---
with tab2:
    if not user:
        st.warning("發起前請先登入。")
    elif not st.session_state.get('confirm_publish', False):
        st.subheader("📢 設定分食份量")
        
        # 基本資料 (簡化，假設你已有 store_map)
        item_name = st.text_input("商品名稱", "草莓大福")
        total_price = st.number_input("商品總價格", min_value=1, value=259)
        total_count = st.number_input("商品總顆數", min_value=1, value=12)
        
        st.divider()
        col1, col2 = st.columns(2)
        with col1:
            self_count = st.number_input("1. 主揪自留幾個？", min_value=1, max_value=total_count, value=5)
        with col2:
            per_pack = st.number_input("2. 幾個為一份？", min_value=1, max_value=total_count, value=5)
        
        # --- 核心邏輯運算 ---
        to_share_count = total_count - self_count
        share_units = to_share_count // per_pack  # 可分出的份數
        remainder = to_share_count % per_pack     # 剩餘孤兒
        
        real_self_count = self_count + remainder  # 主揪實際拿到的個數
        total_units = 1 + share_units             # 主揪(1份) + 別人(share_units份)
        
        # 無條件進位單價
        unit_price = math.ceil(total_price / (1 + share_units))

        st.info(f"💡 運算結果：\n"
                f"- 別人可領：**{share_units} 份** (每份 {per_pack} 顆)\n"
                f"- 主揪實拿：**{real_self_count} 顆** (原留 {self_count} + 孤兒 {remainder})\n"
                f"- 每份金額：**${unit_price} 元**")

        if remainder > 0:
            st.warning(f"注意：因無法整除，剩餘的 {remainder} 顆將自動併入主揪自留數量。")

        if st.button("📝 預覽發布"):
            st.session_state.temp_post = {
                "item": item_name, "price": total_price, "u_price": unit_price,
                "share_units": share_units, "self_units": 1, # 存成份數
                "total_count": total_count, "nickname": user.email.split('@')[0]
            }
            st.session_state.confirm_publish = True
            st.rerun()
    else:
        # 確認發布畫面... (邏輯同前)
        p = st.session_state.temp_post
        st.write("確認無誤後請發布...")
        if st.button("✅ 正式發布"):
            # Insert to Supabase (略)
            st.session_state.confirm_publish = False
            st.rerun()


# --- 4. 頁面邏輯：會員中心 ---
if user and page == "我的會員中心":
    st.title("🛡️ 會員中心")
    
    # 修改暱稱
    with st.expander("📝 修改個人資料"):
        new_nick = st.text_input("我的顯示暱稱", value=get_nickname(user.id))
        if st.button("更新暱稱"):
            supabase.table("profiles").upsert({"id": user.id, "nickname": new_nick}).execute()
            st.success("更新成功！")
            st.rerun()

    m1, m2, m3 = st.tabs(["📢 我的揪團", "🤝 我跟的團", "⌛ 歷史記錄"])
    
    with m1:
        my_groups = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "active").execute().data
        if not my_groups: st.write("目前沒有進行中的揪團。")
        for g in my_groups:
            with st.container(border=True):
                st.write(f"**{g['item_name']}**")
                st.write(f"剩餘份數：{g['remaining_units']} 份")
                if g['has_new_join']: st.warning("🆕 有新成員加入，確認後請手動已讀。")
                c1, c2 = st.columns(2)
                if c1.button("標記通知已讀", key=f"read_{g['id']}"):
                    supabase.table("groups").update({"has_new_join": False}).eq("id", g['id']).execute()
                    st.rerun()
                if c2.button("結案/刪除", key=f"close_{g['id']}"):
                    supabase.table("groups").update({"status": "closed", "has_new_join": False}).eq("id", g['id']).execute()
                    st.rerun()

    with m2:
        followed = supabase.table("group_members").select("*, groups(*)").eq("user_id", user.id).execute().data
        for f in followed:
            g = f['groups']
            if g and g['status'] == 'active':
                st.write(f"✅ 已加入 {g['creator_nickname']} 的「{g['item_name']}」")

    with m3:
        history = supabase.table("groups").select("*").eq("creator_id", user.id).eq("status", "closed").execute().data
        for h in history:
            st.write(f"🌑 {h['item_name']} (於 {h['created_at'][:10]} 結束)")

# --- 5. 頁面邏輯：找分食/發起 ---
elif page == "找分食/發起":
    st.title("🛒 分食趣-現場媒合")
    tab1, tab2 = st.tabs(["🔍 找分食清單", "📢 我要發起揪團"])

    with tab1:
        # 功能 1：手動更新按鈕
        col_title, col_refresh = st.columns([4, 1])
        col_title.subheader("現場待領清單")
        if col_refresh.button("🔄 刷新清單"):
            st.rerun()

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
                            # 顯示每份是多少數量
                            qty_per_unit = item['total_units'] // (item['remaining_units'] + item['self_units']) # 簡化計算
                            st.write(f"💵 價格：**${int(item['unit_price'])}** / 份")
                        with col_btn:
                            st.metric("剩餘", f"{item['remaining_units']} 份")
                            if st.button(f"我要 +1 份", key=f"join_{item['id']}"):
                                if not user: st.error("請先登入！")
                                elif user.id == item['creator_id']: st.warning("這是你發起的喔！")
                                else:
                                    new_remain = item['remaining_units'] - 1
                                    new_status = 'active' if new_remain > 0 else 'closed'
                                    # 更新並觸發通知
                                    supabase.table("groups").update({
                                        "remaining_units": new_remain, 
                                        "status": new_status,
                                        "has_new_join": True 
                                    }).eq("id", item['id']).execute()
                                    supabase.table("group_members").insert({"group_id": item['id'], "user_id": user.id}).execute()
                                    st.success(f"✅ 成功加入！已通知主揪。")
                                    st.balloons()
                                    st.rerun()
        except Exception as e: st.error(f"讀取失敗: {e}")

    with tab2:
        if not user:
            st.warning("🛑 發起揪團前請先登入。")
        else:
            if not st.session_state.confirm_publish:
                st.subheader("📢 設定揪團內容")
                
                # 店家與商品選單
                stores_res = supabase.table("stores").select("*").execute().data
                store_map = {s['branch_name']: s['id'] for s in stores_res}
                selected_store = st.selectbox("在哪間分店？", list(store_map.keys()))
                pops = supabase.table("popular_items").select("*").execute().data
                item_name = st.selectbox("商品名稱", [p['name'] for p in pops])
                
                # 功能 2：修改數量邏輯
                price = st.number_input("商品總價格", min_value=1, value=259)
                total_count = st.number_input("商品總個數 (如: 12顆)", min_value=1, value=12)
                
                st.divider()
                st.write("🔧 **分食單位設定**")
                col_a, col_b = st.columns(2)
                per_pack = col_a.number_input("幾顆為一份？", min_value=1, max_value=total_count, value=3)
                
                # 計算總份數
                total_parts = total_count // per_pack
                st.caption(f"💡 總共可分為 {total_parts} 份")
                
                my_stay_parts = col_b.number_input("主揪自留幾份？", min_value=1, max_value=total_parts, value=1)
                others_parts = total_parts - my_stay_parts
                
                st.metric("開放別人領取", f"{others_parts} 份")
                
                # 每份價格計算
                u_price = math.ceil(price / total_parts)
                st.info(f"💰 每份金額約為：${u_price} 元")

                if st.button("📝 檢查預覽", use_container_width=True):
                    st.session_state.temp_post = {
                        "item": item_name, "price": price, "u_price": u_price,
                        "others_parts": others_parts, "my_parts": my_stay_parts, 
                        "store_id": store_map[selected_store], "total_count": total_count
                    }
                    st.session_state.confirm_publish = True
                    st.rerun()
            else:
                p = st.session_state.temp_post
                st.subheader("📢 第二步：確認發布")
                st.warning(f"確認：{p['item']}\n總個數 {p['total_count']} 顆，分為 {p['my_parts'] + p['others_parts']} 份。\n您留 {p['my_parts']} 份，求分 {p['others_parts']} 份，每份 ${p['u_price']}。")
                
                c1, c2 = st.columns(2)
                if c1.button("❌ 修改內容"):
                    st.session_state.confirm_publish = False
                    st.rerun()
                if c2.button("✅ 正式發布", type="primary"):
                    new_data = {
                        "creator_id": user.id,
                        "creator_nickname": get_nickname(user.id),
                        "store_id": p['store_id'],
                        "item_name": p['item'],
                        "total_price": p['price'],
                        "total_units": p['total_count'], # 總顆數
                        "unit_price": p['u_price'],     # 每份單價
                        "remaining_units": p['others_parts'], # 改存份數
                        "self_units": p['my_parts'],      # 改存份數
                        "status": "active"
                    }
                    supabase.table("groups").insert(new_data).execute()
                    st.success("發布成功！")
                    st.balloons()
                    st.session_state.confirm_publish = False
                    st.rerun()
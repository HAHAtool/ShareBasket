import streamlit as st
from supabase import create_client, Client
import os
import math

# 1. 安全讀取 Secrets
url = st.secrets.get("SUPABASE_URL")
key = st.secrets.get("SUPABASE_KEY")

if not url or not key:
    st.error("❌ 雲端 Secrets 沒設定好，請檢查 Streamlit Cloud 設定。")
    st.stop()

# 2. 連接資料庫
try:
    supabase: Client = create_client(url, key)
except Exception as e:
    st.error(f"❌ 連接資料庫失敗: {e}")
    st.stop()

st.title("🛒 好市多分食現場媒合")

tab1, tab2 = st.tabs(["🔍 我要分食", "📢 我要發起"])

# --- Tab 1: 顯示清單 ---
with tab1:
    try:
        res = supabase.table("groups").select("*, stores(branch_name)").eq("status", "active").execute()
        items = res.data
        if not items:
            st.info("目前沒人在揪喔！")
        else:
            for item in items:
                with st.container(border=True):
                    st.write(f"### {item['item_name']} (剩 {item['remaining_units']})")
                    st.write(f"📍 {item['stores']['branch_name']} | 單價: ${item['unit_price']}")
                    if st.button(f"我要 +1", key=item['id']):
                        # 更新邏輯
                        new_remain = item['remaining_units'] - 1
                        st.success("成功！請與發起人交貨。")
                        supabase.table("groups").update({"remaining_units": new_remain}).eq("id", item['id']).execute()
                        st.rerun()
    except Exception as e:
        st.error(f"讀取清單出錯: {e}")

# --- Tab 2: 發起 ---
with tab2:
    try:
        # 讀取商店
        stores = supabase.table("stores").select("*").execute().data
        store_map = {s['branch_name']: s['id'] for s in stores}
        sel_store = st.selectbox("在哪間店？", list(store_map.keys()))
        
        # 讀取常用商品
        pops = supabase.table("popular_items").select("*").execute().data
        pop_names = [p['name'] for p in pops]
        sel_item = st.selectbox("想分什麼？", pop_names)
        
        price = st.number_input("總價", value=259)
        units = st.number_input("總數", value=12)
        u_price = math.ceil(price / units)
        
        if st.button("🚀 確認發布", use_container_width=True):
            new_data = {
                "creator_nickname": "阿肥",
                "store_id": store_map[sel_store],
                "item_name": sel_item,
                "total_price": price,
                "total_units": units,
                "unit_price": u_price,
                "remaining_units": units
            }
            supabase.table("groups").insert(new_data).execute()
            st.success("發布成功！")
            st.rerun()
    except Exception as e:
        st.error(f"發起功能出錯: {e}")

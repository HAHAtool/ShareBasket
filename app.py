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

# --- 發起分購的優化邏輯 ---
with tab2:
    st.subheader("📢 發起新揪團")
    
    # 數量分配
    total_u = st.number_input("商品總入數", value=12)
    my_u = st.number_input("主揪自留幾顆？", value=6, max_value=total_u)
    others_u = total_u - my_u
    
    st.write(f"💡 開放鄰居認購：**{others_u}** 顆")
    
    # 兩段式確認
    if st.button("📝 預覽發布內容"):
        st.warning(f"確認發布：{sel_item}，總價 ${price}。您留 {my_u} 顆，求分 {others_u} 顆。")
        
        if st.button("🚀 確認正式發布"):
            # 執行寫入資料庫
            # ... (supabase.table("groups").insert(...)
            st.success(f"🎉 {sel_item} ${price} 求分 {others_u} 顆發布成功！")
            st.balloons()
    except Exception as e:
        st.error(f"發起功能出錯: {e}")


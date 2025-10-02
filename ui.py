import streamlit as st
import pandas as pd
import plotly.express as px
import plotly.graph_objects as go
from db import get_db

def kpi_cards():
    """Display KPI summary cards."""
    try:
        with st.container():
            c1, c2, c3, c4 = st.columns(4)
            with get_db() as con:
                total_members = con.execute("SELECT COUNT(*) FROM members").fetchone()[0]
                total_in = con.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='inflow'"
                ).fetchone()[0]
                total_out = con.execute(
                    "SELECT COALESCE(SUM(amount), 0) FROM transactions WHERE type='outflow'"
                ).fetchone()[0]
                profit = con.execute(
                    "SELECT COUNT(*) FROM members WHERE payout >= paid AND paid > 0"
                ).fetchone()[0]
            
            loss = max(0, total_members - profit)

            c1.markdown(
                f"<div class='kpi'><h3>মোট সদস্য</h3><div class='val'>{total_members}</div></div>", 
                unsafe_allow_html=True
            )
            c2.markdown(
                f"<div class='kpi'><h3>মোট ইনফ্লো</h3><div class='val'>৳{int(total_in):,}</div></div>", 
                unsafe_allow_html=True
            )
            c3.markdown(
                f"<div class='kpi'><h3>মোট পেআউট</h3><div class='val'>৳{int(total_out):,}</div></div>", 
                unsafe_allow_html=True
            )
            c4.markdown(
                f"<div class='kpi'><h3>লাভ/ক্ষতি</h3><div class='val'>🙂 {profit} / 🙁 {loss}</div></div>", 
                unsafe_allow_html=True
            )
    except Exception as e:
        st.error(f"Error loading KPIs: {e}")

def inflow_outflow_chart():
    """Display inflow vs outflow time series chart."""
    try:
        with get_db() as con:
            df = pd.read_sql_query(
                """
                SELECT 
                    datetime(ts, 'unixepoch') as date,
                    SUM(CASE WHEN type='inflow' THEN amount ELSE 0 END) AS inflow,
                    SUM(CASE WHEN type='outflow' THEN amount ELSE 0 END) AS outflow
                FROM transactions 
                GROUP BY date 
                ORDER BY ts
                """, 
                con
            )
        
        if df.empty:
            st.info("No transaction data yet.")
            return
        
        df["net"] = df["inflow"] - df["outflow"]
        
        fig = go.Figure()
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["inflow"], 
            name="ইনফ্লো", mode="lines+markers", 
            line=dict(color="#34D399", width=2)
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["outflow"], 
            name="পেআউট", mode="lines+markers", 
            line=dict(color="#F59E0B", width=2)
        ))
        fig.add_trace(go.Scatter(
            x=df["date"], y=df["net"], 
            name="নিট", mode="lines+markers", 
            line=dict(color="#60A5FA", width=2)
        ))
        
        fig.update_layout(
            template="plotly_white", 
            height=360, 
            margin=dict(l=10, r=10, t=30, b=10),
            xaxis_title="Date",
            yaxis_title="Amount (৳)"
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error loading chart: {e}")

def level_bar_chart():
    """Display member distribution by level."""
    try:
        with get_db() as con:
            df = pd.read_sql_query(
                "SELECT level, COUNT(*) AS cnt FROM members GROUP BY level ORDER BY level", 
                con
            )
        
        if df.empty:
            st.info("No members yet.")
            return
        
        fig = px.bar(
            df, x="level", y="cnt", 
            color="level",
            color_discrete_sequence=px.colors.sequential.YlOrRd,
            height=320,
            labels={"level": "Level", "cnt": "Members"}
        )
        fig.update_layout(
            template="plotly_white", 
            showlegend=False, 
            margin=dict(l=10, r=10, t=30, b=10)
        )
        st.plotly_chart(fig, use_container_width=True)
    except Exception as e:
        st.error(f"Error loading level chart: {e}")

def tree_view(limit_edges: int = 200):
    """Display pyramid structure as text tree."""
    try:
        with get_db() as con:
            roots = con.execute(
                "SELECT id FROM members WHERE parent IS NULL ORDER BY joined_at LIMIT 10"
            ).fetchall()
            
            if not roots:
                st.info("Tree is empty.")
                return
            
            st.subheader("🌳 Pyramid Structure")
            
            def print_tree(member_id, level=0, max_depth=4):
                if level > max_depth:
                    return
                
                with get_db() as con:
                    member = con.execute(
                        "SELECT id, level, payout FROM members WHERE id = ?",
                        (member_id,)
                    ).fetchone()
                    
                    if member:
                        indent = "  " * level
                        st.text(f"{indent}├─ {member['id']} (L{member['level']}, ৳{int(member['payout'])})")
                        
                        children = con.execute(
                            "SELECT id FROM members WHERE parent = ? ORDER BY joined_at LIMIT 10",
                            (member_id,)
                        ).fetchall()
                        
                        for child in children:
                            print_tree(child['id'], level + 1, max_depth)
            
            for root in roots[:3]:
                print_tree(root['id'])
                
    except Exception as e:
        st.error(f"Error loading tree: {e}")

def members_table():
    """Display members data table."""
    try:
        with get_db() as con:
            df = pd.read_sql_query(
                """
                SELECT 
                    id, level, parent,
                    datetime(joined_at, 'unixepoch') as joined_date,
                    paid, payout,
                    CASE 
                        WHEN payout >= paid AND paid > 0 THEN '🟢 Profit'
                        WHEN paid > 0 THEN '🔴 Loss'
                        ELSE '⚪ Pending'
                    END as status
                FROM members 
                ORDER BY joined_at DESC 
                LIMIT 100
                """,
                con
            )
        
        if df.empty:
            st.info("No members registered yet.")
            return
        
        st.subheader("📋 Members List")
        st.dataframe(
            df,
            use_container_width=True,
            hide_index=True,
            column_config={
                "id": "Member ID",
                "level": st.column_config.NumberColumn("Level", format="%d"),
                "parent": "Parent ID",
                "joined_date": "Joined",
                "paid": st.column_config.NumberColumn("Paid (৳)", format="৳%d"),
                "payout": st.column_config.NumberColumn("Payout (৳)", format="৳%.2f"),
                "status": "Status"
            }
        )
    except Exception as e:
        st.error(f"Error loading members table: {e}")

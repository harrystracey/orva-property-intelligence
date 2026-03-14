"""
AI Property Research Agent - Streamlit Interface
Uses Claude + Playwright to research PropertyMonitor.ae
"""

import streamlit as st
import asyncio
import sys

# Page config
st.set_page_config(
    page_title="AI Property Research",
    page_icon="🔍",
    layout="wide"
)

# Custom CSS
st.markdown("""
<style>
.main {background-color: #ffffff; font-family: 'Segoe UI', sans-serif;}
.success-box {background-color: #d4edda; padding: 1rem; border-radius: 8px; border-left: 4px solid #28a745;}
.error-box {background-color: #f8d7da; padding: 1rem; border-radius: 8px; border-left: 4px solid #dc3545;}
.info-box {background-color: #e7f3ff; padding: 1rem; border-radius: 8px; border-left: 4px solid #0066cc;}
</style>
""", unsafe_allow_html=True)

# Header
st.title("🔍 AI Property Research Agent")
st.caption("Powered by Claude + PropertyMonitor.ae | Palm Jumeirah Market Intelligence")

# Sidebar - Configuration & Status
with st.sidebar:
    st.header("⚙️ System Status")
    
    # Check configuration
    config_valid = False
    try:
        import config
        
        if not config.ANTHROPIC_API_KEY:
            st.error("❌ Missing Anthropic API Key")
            st.warning("Add your API key to `.env` file:")
            st.code("ANTHROPIC_API_KEY=sk-ant-...")
            st.link_button("Get API Key", "https://console.anthropic.com/")
        else:
            config_valid = True
            st.success("✅ Configuration Valid")
            st.info(f"📧 PM Account: {config.PROPERTYMONITOR_EMAIL}")
            
    except Exception as e:
        st.error(f"❌ Config Error: {str(e)}")
    
    st.divider()
    
    # Example queries
    st.header("📋 Example Queries")
    st.markdown("""
**Service Charges:**
- *What's the service charge for Tiara?*
- *Service charge for Shoreline 5?*

**Transactions:**
- *Recent sales in Oceana*
- *Rental transactions in Azure*

**Market Data:**
- *Average price per sqft in Serenia*
- *How many units sold in Fairmont?*
    """)
    
    st.divider()
    
    # Building reference
    with st.expander("🏢 Building Names"):
        st.markdown("""
**Shoreline Apartments:**
- Shoreline 1-20
- Al Basri = Shoreline 1
- Al Hallawi = Shoreline 5
- Al Janahi = Shoreline 12

**Other Buildings:**
- Tiara, Azure, Oceana
- Anantara, Kempinski
- Fairmont, Serenia
- Balqis, Palm Beach Towers
        """)
    
    st.divider()
    st.caption("⚠️ Browser opens visibly for debugging")
    st.caption("🔒 Credentials stored locally only")

# Main interface
st.markdown("---")

# Query input
query = st.text_area(
    "🔎 Ask a question about Palm Jumeirah properties:",
    placeholder="e.g., What's the service charge for Shoreline 1?\ne.g., Show me recent sales in Tiara Residences",
    height=100,
    key="query_input"
)

# Research button
col1, col2, col3 = st.columns([1, 2, 1])
with col2:
    research_clicked = st.button(
        "🚀 Start Research", 
        type="primary", 
        use_container_width=True,
        disabled=not config_valid
    )

# Process research
if research_clicked:
    if not query.strip():
        st.warning("⚠️ Please enter a question first")
    else:
        # Import agent here to avoid import errors if config is invalid
        from scraper_agent import PropertyMonitorAgent
        
        # Results container
        with st.status("🤖 Researching PropertyMonitor.ae...", expanded=True) as status:
            st.write("🚀 Initializing AI agent...")
            st.write("🌐 Launching browser (this window will open)...")
            
            # Run async research
            agent = PropertyMonitorAgent()
            
            async def run_research():
                return await agent.research_query(query)
            
            # Execute the async function
            try:
                result = asyncio.run(run_research())
                
                # Display steps as they complete
                for step in result.get('steps', []):
                    st.write(step)
                
                if result['success']:
                    status.update(label="✅ Research Complete!", state="complete")
                else:
                    status.update(label="❌ Research Failed", state="error")
                    
            except Exception as e:
                result = {
                    'success': False,
                    'answer': f'Error: {str(e)}',
                    'steps': [f'❌ Error: {str(e)}'],
                    'building': 'Unknown'
                }
                status.update(label="❌ Error Occurred", state="error")
        
        # Display results
        st.markdown("---")
        st.subheader("📊 Research Results")
        
        col1, col2 = st.columns([3, 1])
        
        with col1:
            if result['success']:
                st.markdown(f"""
<div class="success-box">
<h4>✅ Answer</h4>
{result['answer']}
</div>
                """, unsafe_allow_html=True)
            else:
                st.markdown(f"""
<div class="error-box">
<h4>❌ Error</h4>
{result['answer']}
</div>
                """, unsafe_allow_html=True)
        
        with col2:
            st.markdown(f"""
<div class="info-box">
<h4>ℹ️ Details</h4>
<b>Building:</b> {result.get('building', 'N/A')}<br>
<b>Section:</b> {result.get('section', 'N/A')}<br>
<b>Status:</b> {'Success' if result['success'] else 'Failed'}<br>
<b>Steps:</b> {len(result.get('steps', []))}
</div>
            """, unsafe_allow_html=True)
        
        # Show execution steps
        with st.expander("📝 Execution Log", expanded=False):
            for i, step in enumerate(result.get('steps', []), 1):
                st.write(f"{i}. {step}")

# Footer
st.markdown("---")
col1, col2, col3 = st.columns(3)
with col1:
    st.caption("🔒 Secure - Credentials never leave your machine")
with col2:
    st.caption("🤖 Powered by Claude AI")
with col3:
    st.caption("📊 Data from PropertyMonitor.ae")

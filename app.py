import streamlit as st
import requests
import base64
from streamlit_cropper import st_cropper
from PIL import Image
import io
import os
import boto3
import pandas as pd
import plotly.express as px

SIMILARITY_SVC_URL = os.getenv("SIMILARITY_SEARCH_SVC")
IMAGE_DOWNLOAD_SVC_URL = os.getenv("IMAGE_DOWNLOAD_SVC")
API_KEY = os.getenv("API_KEY")
CC_ANALYSIS_FILE_PATH = os.getenv("CC_ANALYSIS_FILE_PATH")

# AWS credentials
AWS_ACCESS_KEY_ID = os.getenv("AWS_ACCESS_KEY_ID")
AWS_SECRET_ACCESS_KEY = os.getenv("AWS_SECRET_ACCESS_KEY")
AWS_REGION = os.getenv("AWS_REGION", "us-east-1")

# Download CSV from S3 and convert to DataFrame
def download_csv_from_s3(s3_path):
    """Download CSV file from S3 and return as DataFrame"""
    if not s3_path:
        return None
    
    # Parse S3 path (format: s3://bucket/key)
    if s3_path.startswith('s3://'):
        s3_path = s3_path[5:]
    parts = s3_path.split('/', 1)
    bucket = parts[0]
    key = parts[1] if len(parts) > 1 else ''
    
    # Create S3 client with credentials if provided, otherwise use default credential chain
    if AWS_ACCESS_KEY_ID and AWS_SECRET_ACCESS_KEY:
        s3_client = boto3.client(
            's3',
            aws_access_key_id=AWS_ACCESS_KEY_ID,
            aws_secret_access_key=AWS_SECRET_ACCESS_KEY,
            region_name=AWS_REGION
        )
    else:
        s3_client = boto3.client('s3', region_name=AWS_REGION)
    
    obj = s3_client.get_object(Bucket=bucket, Key=key)
    df = pd.read_csv(io.BytesIO(obj['Body'].read()))
    return df

# Load the CSV file
cc_analysis_df = download_csv_from_s3(CC_ANALYSIS_FILE_PATH) if CC_ANALYSIS_FILE_PATH else None

st.set_page_config(page_title="Trademark Analysis", layout="wide")
# Legal disclaimer
st.warning("⚠️ **Disclaimer**: This tool is for informational purposes only and does not constitute legal advice. For trademark matters, please consult with a qualified intellectual property attorney.")

# Sidebar navigation with selectbox
st.sidebar.title("🔧 Navigation")
page = st.sidebar.selectbox(
    "Choose a tool:",
    ["Logo Similarity", "Coordinate Class Calculator"],
    key="nav_selectbox"
)

# ===== LOGO SIMILARITY PAGE =====
if page == "Logo Similarity":
    st.title("Trademark/Logo Similarity Search (USPTO Trademarks only)")
    
    # Option selection
    st.subheader("Trademark Similarity By:")
    search_type = st.radio(
        "Select search method:",
        ["Image (Upload Image)", "Image Description"],
        key="search_method_radio",
        label_visibility="collapsed"
    )

    cropped_img = None
    description_text = ""

    if search_type == "Image (Upload Image)":
        # File upload widget
        uploaded_file = st.file_uploader(
            "Upload an image file",
            type=["jpg", "jpeg", "png", "gif", "bmp"],
            key="image_uploader"
        )
        
        if uploaded_file is not None:
            # Display and crop the image
            img = Image.open(uploaded_file)
            
            # Create two columns for cropper and preview
            crop_col, preview_col = st.columns([2, 1])
            
            with crop_col:
                st.write("### Original Image:")
                cropped_img = st_cropper(img, realtime_update=True, box_color='#FF0004')
            
            with preview_col:
                st.write("### Selected Image Preview")
                if cropped_img is not None:
                    st.image(cropped_img, use_container_width=True)

    else:  # Describe Image
        description_text = st.text_area(
            "Describe the trademark image:",
            placeholder="Enter a description of the trademark image (e.g., 'A chef in an apron')",
            height=100,
            key="description_text_area"
        )

    # Goods and services description input (optional)
    st.write("### Goods and Services (Optional)")
    gs_desc = st.text_area(
        "Describe the goods and services for this trademark:",
        placeholder="Describe goods and services(e.g., sell sandwiches online and in-store)",
        help="This helps provide additional context for the trademark search.",
        height=80,
        key="gs_desc_text_area"
    )

    # Search button
    if st.button("Search Similar Marks", key="search_button"):
        if search_type == "Image (Upload Image)" and cropped_img is not None:
            with st.spinner("Searching for similar marks..."):
                try:
                    # Convert cropped image to bytes for upload
                    img_byte_arr = io.BytesIO()
                    cropped_img.save(img_byte_arr, format='PNG')    
                    img_byte_arr.seek(0)
                    
                    # Prepare the POST request - send as file upload with goods/services description
                    files = {"image": ("cropped_image.png", img_byte_arr, "image/png")}
                    # files = {"image": ("cropped_image.png", img_byte_arr.getvalue(), "image/png")}
                    data = {"gs_desc": gs_desc.strip()} if gs_desc.strip() else {}
                    headers = {"x-api-key": API_KEY} if API_KEY else {}
                    response = requests.post(
                        f"{SIMILARITY_SVC_URL}/similarMarksByImage",
                        files=files,
                        data=data,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        st.success("Search completed successfully!")
                        result = response.json()
                        
                        if "similar_marks" in result and result["similar_marks"]:
                            st.subheader(f"Found {len(result['similar_marks'])} similar marks")
                            
                            # Get design codes from response
                            all_design_codes = result.get("design_codes", [])
                            
                            # Create layout with main content and sidebar
                            main_col, side_col = st.columns([3, 1])
                            
                            with main_col:
                                # Create columns for cards layout
                                cols = st.columns(3)  # 3 cards per row
                                
                                for idx, mark in enumerate(result["similar_marks"]):
                                    col = cols[idx % 3]
                                    
                                    with col:
                                        with st.container():
                                            st.markdown("---")
                                            # Trademark image from USPTO
                                            image_url = f"{IMAGE_DOWNLOAD_SVC_URL}/{mark.get('serial_no')}/large"
                                        
                                            # Create a fixed height container for the image
                                            st.markdown(f"""
                                            <div style="height: 150px; display: flex; align-items: center; justify-content: center; overflow: hidden;">
                                                <img src="{image_url}" style="max-width: 180px; max-height: 150px; object-fit: contain;" />
                                            </div>
                                            """, unsafe_allow_html=True)
                                            
                                            # Mark details
                                            st.write(f"**Serial No:** {mark.get('serial_no', 'N/A')}")
                                            st.write(f"**Filing Date:** {mark.get('filing_dt', 'N/A')}")
                                            st.write(f"**Mark ID:** {mark.get('mark_id_char', 'N/A') or 'N/A'}")
                                            st.write(f"**Similarity Score:** {mark.get('similarity_score', 0):.4f}")
                            
                            with side_col:
                                st.subheader("Design Codes")
                                if all_design_codes:
                                    for code in sorted(all_design_codes):
                                        st.write(f"• {code}")
                                else:
                                    st.write("No design codes found")
                                        
                        else:
                            st.info("No similar marks found.")
                    else:
                        st.error(f"Error: {response.status_code}")
                        
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
                        
        elif search_type == "Image Description" and description_text.strip():
            with st.spinner("Searching for similar marks..."):
                try:
                    # Prepare the POST request for description with goods/services description
                    data = {"description": description_text.strip()}
                    if gs_desc.strip():
                        data["gs_desc"] = gs_desc.strip()
                    headers = {"x-api-key": API_KEY} if API_KEY else {}
                    response = requests.post(
                        f"{SIMILARITY_SVC_URL}/similarMarksByDescription",
                        data=data,
                        headers=headers
                    )
                    
                    if response.status_code == 200:
                        st.success("Search completed successfully!")
                        result = response.json()
                        
                        if "similar_marks" in result and result["similar_marks"]:
                            st.subheader(f"Found {len(result['similar_marks'])} similar marks")
                            
                            # Get design codes from response
                            all_design_codes = result.get("design_codes", [])
                            
                            # Create layout with main content and sidebar
                            main_col, side_col = st.columns([3, 1])
                            
                            with main_col:
                                # Create columns for cards layout
                                cols = st.columns(3)  # 3 cards per row
                                
                                for idx, mark in enumerate(result["similar_marks"]):
                                    col = cols[idx % 3]
                                    
                                    with col:
                                        with st.container():
                                            st.markdown("---")
                                            # Trademark image from USPTO
                                            image_url = f"{IMAGE_DOWNLOAD_SVC_URL}/{mark.get('serial_no')}/large"
                                    
                                            # Create a fixed height container for the image
                                            st.markdown(f"""
                                            <div style="height: 150px; display: flex; align-items: center; justify-content: center; overflow: hidden;">
                                                <img src="{image_url}" style="max-width: 180px; max-height: 150px; object-fit: contain;" />
                                            </div>
                                            """, unsafe_allow_html=True)
                                            
                                            # Mark details
                                            st.write(f"**Serial No:** {mark.get('serial_no', 'N/A')}")
                                            st.write(f"**Filing Date:** {mark.get('filing_dt', 'N/A')}")
                                            st.write(f"**Mark ID:** {mark.get('mark_id_char', 'N/A') or 'N/A'}")
                                            st.write(f"**Similarity Score:** {mark.get('similarity_score', 0):.4f}")
                            
                            with side_col:
                                st.subheader("Design Codes")
                                if all_design_codes:
                                    for code in sorted(all_design_codes):
                                        st.write(f"• {code}")
                                else:
                                    st.write("No design codes found")
                                        
                        else:
                            st.info("No similar marks found.")
                    else:
                        st.error(f"Error: {response.status_code} - {response.text}")
                        
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
        else:
            if search_type == "Image (Upload Image)":
                st.warning("Please upload an image file and crop it first.")
            else:
                st.warning("Please enter a description of the trademark image.")

# ===== COORDINATE CLASS CALCULATOR PAGE =====
elif page == "Coordinate Class Calculator":
    st.title("Coordinate Class Calculator")
    
    if cc_analysis_df is not None:
        st.write("### Class Co-occurrence Probability Heatmap")
        st.write("This heatmap shows P(B|A): the probability that an applicant will file for Class B given it has filed for Class A for all pairs of classes. Use this to identify potential coordinated classes based on historical filing patterns.")
        
        # Pivot the dataframe to create a matrix for heatmap
        heatmap_data = cc_analysis_df.pivot(
            index='Class A',
            columns='Class B',
            values='P(B|A) (probability % that an application will file for class B given it has filed for class A)'
        )
        
        # Sort both axes by extracting the numeric class number from the string
        # Assumes format like "1 (something)", "2 (something)", etc.
        def extract_class_number(class_str):
            """Extract numeric class number from string like '1 (something)'"""
            try:
                return int(str(class_str).split()[0])
            except:
                return 0
        
        # Sort index and columns numerically
        sorted_index = sorted(heatmap_data.index, key=extract_class_number)
        sorted_columns = sorted(heatmap_data.columns, key=extract_class_number)
        heatmap_data = heatmap_data.reindex(index=sorted_index, columns=sorted_columns)
        
        # Custom binning and coloring scheme
        bins = [0, 5, 10, 15, 20, 25, 50, 100]
        colors = [
            '#ffffcc',  # 0-5% (very light yellow)
            '#a6cee3',  # 5-10% (light blue)
            '#1f78b4',  # 10-15% (blue)
            '#b2df8a',  # 15-20% (light green)
            '#fee08b',  # 20-25% (light orange)
            '#fdae61',  # 25-50% (orange)
            '#d73027',  # 50-100% (red)
        ]
        
        # Create discrete colorscale for Plotly
        # Format: [[position, color], [position, color], ...]
        colorscale = []
        for i in range(len(bins) - 1):
            # Normalize bin edges to [0, 1]
            pos_start = bins[i] / 100.0
            pos_end = bins[i + 1] / 100.0
            
            # Add color at start and end of bin (creates discrete steps)
            if i == 0:
                colorscale.append([pos_start, colors[i]])
            colorscale.append([pos_end, colors[i]])
            if i < len(colors) - 1:
                colorscale.append([pos_end, colors[i + 1]])
        
        # Create interactive heatmap using plotly
        fig = px.imshow(
            heatmap_data,
            labels=dict(x="Class B", y="Class A", color="Probability (%)"),
            x=heatmap_data.columns,
            y=heatmap_data.index,
            color_continuous_scale=colorscale,
            aspect="auto",
            title="Co-occurrence Probability: P(Class B | Class A)",
            zmin=0,
            zmax=100
        )
        
        # Update layout for better readability and visible grid lines
        fig.update_xaxes(
            side="bottom",
            showgrid=True,
            gridwidth=2,
            gridcolor='white',
            tickmode='linear',
            dtick=1
        )
        fig.update_yaxes(
            showgrid=True,
            gridwidth=2,
            gridcolor='white',
            tickmode='linear',
            dtick=1
        )
        fig.update_layout(
            width=1000,
            height=1000,
            xaxis_title="Class B (Potential Coordinated Class)",
            yaxis_title="Class A (Given Class)"
        )
        
        # Add white borders around cells for better visibility
        fig.update_traces(
            xgap=1,
            ygap=1
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Filter Section
        st.write("---")
        st.write("### 🔍 Filter Coordinated Classes by Threshold")
        st.write("Select a Class A and threshold to find all Class B values with probability above the threshold")
        
        col1, col2, col3 = st.columns([2, 2, 1])
        
        with col1:
            # Get unique classes sorted numerically
            unique_classes = sorted(cc_analysis_df['Class A'].unique(), key=extract_class_number)
            selected_class_a = st.selectbox(
                "Select Class A:",
                options=unique_classes,
                key="class_a_selector"
            )
        
        with col2:
            threshold = st.slider(
                "Probability Threshold (%):",
                min_value=0,
                max_value=100,
                value=20,
                step=1,
                key="threshold_slider"
            )
        
        with col3:
            st.write("")  # spacing
            st.write("")  # spacing
            filter_button = st.button("🔎 Filter", key="filter_button")
        
        if filter_button:
            # Filter the data
            filtered_data = cc_analysis_df[
                (cc_analysis_df['Class A'] == selected_class_a) & 
                (cc_analysis_df['P(B|A) (probability % that an application will file for class B given it has filed for class A)'] > threshold)
            ].copy()
            
            if not filtered_data.empty:
                # Sort by probability descending
                filtered_data = filtered_data.sort_values(
                    by='P(B|A) (probability % that an application will file for class B given it has filed for class A)',
                    ascending=False
                )
                
                st.success(f"Found {len(filtered_data)} coordinated classes for **{selected_class_a}** with probability > {threshold}%")
                
                # Display results in a nice format
                st.write(f"#### Coordinated Classes for {selected_class_a}")
                
                # Create a cleaner display dataframe
                display_df = filtered_data[['Class B', 'P(B|A) (probability % that an application will file for class B given it has filed for class A)']].copy()
                display_df.columns = ['Class B', 'Probability (%)']
                display_df['Probability (%)'] = display_df['Probability (%)'].round(2)
                display_df.reset_index(drop=True, inplace=True)
                display_df.index = display_df.index + 1  # Start index from 1
                
                st.dataframe(display_df, use_container_width=True)
            else:
                st.info(f"No coordinated classes found for **{selected_class_a}** with probability > {threshold}%")
        
        # Optional: Show raw data table
        with st.expander("📊 View Raw Data"):
            st.dataframe(cc_analysis_df, use_container_width=True)
    else:
        st.warning("⚠️ Class co-occurrence data is not available. Please configure CC_ANALYSIS_FILE_PATH environment variable.")
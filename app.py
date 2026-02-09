import streamlit as st
import requests
import base64
from streamlit_cropper import st_cropper
from PIL import Image
import io
import os

SIMILARITY_SVC_URL = os.getenv("SIMILARITY_SEARCH_SVC")
IMAGE_DOWNLOAD_SVC_URL = os.getenv("IMAGE_DOWNLOAD_SVC")
API_KEY = os.getenv("API_KEY")

st.set_page_config(page_title="Trademark Analysis", layout="wide")

# Main content
st.title("Trademark/Logo Similarity Search(USPTO Trademarks only)")

# Legal disclaimer
st.warning("⚠️ **Disclaimer**: This tool is for informational purposes only and does not constitute legal advice. For trademark matters, please consult with a qualified intellectual property attorney.")

# Option selection
search_type = st.radio(
    "Choose search method:",
    ["Upload Image", "Describe Image"]
)

cropped_img = None
description_text = ""

if search_type == "Upload Image":
    # File upload widget
    uploaded_file = st.file_uploader(
        "Upload an image file",
        type=["jpg", "jpeg", "png", "gif", "bmp"]
    )
    
    if uploaded_file is not None:
        # Display and crop the image
        img = Image.open(uploaded_file)
        st.write("Crop your image:")
        cropped_img = st_cropper(img, realtime_update=True, box_color='#FF0004')
        
        # Display cropped preview
        st.write("Preview of cropped image:")
        st.image(cropped_img, width=300)

else:  # Describe Image
    description_text = st.text_area(
        "Describe the trademark image:",
        placeholder="Enter a description of the trademark image (e.g., 'A chef in an apron')",
        height=100
    )

# Goods and services description input (optional)
st.write("### Goods and Services (Optional)")
gs_desc = st.text_area(
    "Describe the goods and services for this trademark:",
    placeholder="Describe goods and services(e.g., sell sandwiches online and in-store)",
    help="This helps provide additional context for the trademark search.",
    height=80
)

# Search button
if st.button("Search Similar Marks"):
    if search_type == "Upload Image" and cropped_img is not None:
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
                                        image_url = f"{IMAGE_DOWNLOAD_SVC_URL}/cases/{mark.get('serial_no')}/mark/image.png"
                                        
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
                    
    elif search_type == "Describe Image" and description_text.strip():
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
                                        image_url = f"{IMAGE_DOWNLOAD_SVC_URL}/cases/{mark.get('serial_no')}/mark/image.png"
                                        
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
        if search_type == "Upload Image":
            st.warning("Please upload an image file and crop it first.")
        else:
            st.warning("Please enter a description of the trademark image.")
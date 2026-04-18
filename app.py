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
from reportlab.lib.pagesizes import letter, A4
from reportlab.lib.units import inch
from reportlab.pdfgen import canvas
from reportlab.platypus import Table, TableStyle, Paragraph, Spacer, PageBreak, SimpleDocTemplate, Image as RLImage
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib import colors
from reportlab.lib.enums import TA_CENTER, TA_LEFT
from io import BytesIO
import requests as req
import asyncio
import aiohttp

SIMILARITY_SVC_URL = os.getenv("SIMILARITY_SEARCH_SVC")
IMAGE_DOWNLOAD_SVC_URL = os.getenv("IMAGE_DOWNLOAD_SVC")
API_KEY = os.getenv("API_KEY")
CC_ANALYSIS_FILE_PATH = os.getenv("CC_ANALYSIS_FILE_PATH")
DESIGN_CODE_DESC_PATH = os.getenv("DESIGN_CODE_DESC_PATH")

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

# Async function to fetch a single image
async def fetch_image_async(session, image_url, serial_no, headers):
    """Fetch a single image asynchronously"""
    try:
        async with session.get(image_url, timeout=aiohttp.ClientTimeout(total=5), headers=headers) as response:
            if response.status == 200:
                content = await response.read()
                # Open image and resize it
                img = Image.open(BytesIO(content))
                img.thumbnail((200, 200), Image.Resampling.LANCZOS)  # Resize to max 200x200
                
                # Convert resized PIL image to BytesIO
                img_buffer = BytesIO()
                img.save(img_buffer, format='PNG')
                img_buffer.seek(0)
                
                # Create RLImage from BytesIO
                mark_img = RLImage(img_buffer, width=0.8*inch, height=0.8*inch)
                return (serial_no, mark_img)
            else:
                return (serial_no, f"[Error {response.status}]")
    except asyncio.TimeoutError:
        return (serial_no, "[Timeout]")
    except Exception as e:
        return (serial_no, "[Image unavailable]")

# Async function to fetch all images concurrently
async def fetch_all_images_async(filtered_marks):
    """Fetch all images concurrently"""
    headers = {
        'User-Agent': 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
        'Accept': 'image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8',
    }
    
    async with aiohttp.ClientSession() as session:
        tasks = []
        for mark in filtered_marks:
            serial_no = str(mark.get('serial_no', 'N/A'))
            image_url = f"{IMAGE_DOWNLOAD_SVC_URL}/{mark.get('serial_no')}/large"
            tasks.append(fetch_image_async(session, image_url, serial_no, headers))
        
        # Execute all tasks concurrently
        results = await asyncio.gather(*tasks, return_exceptions=True)
        return results

# Function to generate PDF with cropped image and results table
def generate_pdf_report(cropped_img, filtered_marks, search_type_used):
    """Generate a PDF report with cropped image and table of candidates"""
    pdf_buffer = BytesIO()
    
    try:
        # Create PDF document
        doc = SimpleDocTemplate(pdf_buffer, pagesize=letter, topMargin=0.5*inch, bottomMargin=0.5*inch)
        elements = []
        styles = getSampleStyleSheet()
        
        # Title style
        title_style = ParagraphStyle(
            'CustomTitle',
            parent=styles['Heading1'],
            fontSize=16,
            textColor=colors.HexColor('#1f78b4'),
            spaceAfter=12,
            alignment=TA_CENTER
        )
        
        # Add title
        title = Paragraph("Trademark/Logo Similarity Search Report", title_style)
        elements.append(title)
        elements.append(Spacer(1, 0.2*inch))
        
        # Add cropped image - convert PIL to BytesIO
        elements.append(Paragraph("<b>Query Image (Cropped):</b>", styles['Heading2']))
        cropped_buffer = BytesIO()
        cropped_img.save(cropped_buffer, format='PNG')
        cropped_buffer.seek(0)
        img_for_pdf = RLImage(cropped_buffer, width=2*inch, height=2*inch)
        elements.append(img_for_pdf)
        elements.append(Spacer(1, 0.3*inch))
        
        # Add results section
        if filtered_marks:
            elements.append(Paragraph(f"<b>Found {len(filtered_marks)} Similar Marks:</b>", styles['Heading2']))
            elements.append(Spacer(1, 0.2*inch))
            
            # Create table data
            table_data = [['Serial No.', 'Trademark Image']]
            
            # Fetch all images concurrently using async
            image_results = asyncio.run(fetch_all_images_async(filtered_marks))
            
            # Process results and add to table
            for serial_no, mark_img in image_results:
                table_data.append([serial_no, mark_img])
            
            # Create table
            table = Table(table_data, colWidths=[1.5*inch, 3*inch])
            table.setStyle(TableStyle([
                ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1f78b4')),
                ('TEXTCOLOR', (0, 0), (-1, 0), colors.whitesmoke),
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
                ('FONTSIZE', (0, 0), (-1, 0), 10),
                ('BOTTOMPADDING', (0, 0), (-1, 0), 12),
                ('BACKGROUND', (0, 1), (-1, -1), colors.beige),
                ('GRID', (0, 0), (-1, -1), 1, colors.black),
                ('ROWHEIGHTS', (0, 0), (-1, -1), 1*inch),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            
            elements.append(table)
        else:
            elements.append(Paragraph("No results to display.", styles['Normal']))
        
        # Build PDF
        doc.build(elements)
        pdf_buffer.seek(0)
        return pdf_buffer
        
    except Exception as e:
        return BytesIO()


cc_analysis_df = download_csv_from_s3(CC_ANALYSIS_FILE_PATH) if CC_ANALYSIS_FILE_PATH else None
design_code_desc_df = download_csv_from_s3(DESIGN_CODE_DESC_PATH) if DESIGN_CODE_DESC_PATH else None

st.set_page_config(page_title="Trademark Analysis", layout="wide")
# Legal disclaimer
st.warning("⚠️ **Disclaimer**: This tool is for informational purposes only and does not constitute legal advice. For trademark matters, please consult with a qualified intellectual property attorney.")

# Sidebar navigation with selectbox
st.sidebar.title("🔧 Navigation")
page = st.sidebar.selectbox(
    "Choose a tool:",
    ["Logo Similarity", "Word Mark Similarity", "Coordinate Class Calculator"],
    key="nav_selectbox"
)

# ===== LOGO SIMILARITY PAGE =====
if page == "Logo Similarity":
    st.title("Trademark/Logo Similarity Search (USPTO Trademarks only)")
    
    # Initialize session state for search results
    if 'search_results' not in st.session_state:
        st.session_state.search_results = None
    if 'search_type_used' not in st.session_state:
        st.session_state.search_type_used = None
    
    # Option selection
    st.subheader("Trademark Similarity By:")
    search_type = st.radio(
        "Select search method:",
        ["Image (Upload Image)", "Image Description"],
        key="search_method_radio",
        label_visibility="collapsed"
    )
    
    # Clear results if search type changes
    if st.session_state.search_type_used and st.session_state.search_type_used != search_type:
        st.session_state.search_results = None
        st.session_state.search_type_used = None

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
                        st.session_state.search_results = result
                        st.session_state.search_type_used = "Image (Upload Image)"
                    else:
                        st.error(f"Error: {response.status_code}")
                        st.session_state.search_results = None
                        
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
                        st.session_state.search_results = result
                        st.session_state.search_type_used = "Image Description"
                    else:
                        st.error(f"Error: {response.status_code} - {response.text}")
                        st.session_state.search_results = None
                        
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
        else:
            if search_type == "Image (Upload Image)":
                st.warning("Please upload an image file and crop it first.")
            else:
                st.warning("Please enter a description of the trademark image.")
    
    # Display results if they exist in session state (outside button block for dynamic filtering)
    if st.session_state.search_results is not None:
        result = st.session_state.search_results
        
        if "similar_marks" in result and result["similar_marks"]:
            st.subheader(f"Found {len(result['similar_marks'])} similar marks")
            
            # Aggregate design codes from all similar marks and count occurrences
            design_code_counts = {}
            for mark in result["similar_marks"]:
                mark_design_codes = mark.get("design_codes", [])
                if mark_design_codes:
                    for code in mark_design_codes:
                        design_code_counts[code] = design_code_counts.get(code, 0) + 1
            
            # Sort design codes by count (descending)
            sorted_design_codes = sorted(design_code_counts.items(), key=lambda x: x[1], reverse=True)
            
            # Create layout with main content and sidebar
            main_col, side_col = st.columns([3, 1])
            
            with side_col:
                st.subheader("Design Codes")
                if sorted_design_codes:
                    st.write("*Click to filter results*")
                    
                    # Add Select All checkbox
                    checkbox_key_suffix = st.session_state.search_type_used.replace(" ", "_").replace("(", "").replace(")", "")
                    select_all_key = f"select_all_{checkbox_key_suffix}"
                    
                    # Initialize select_all state if not exists
                    if select_all_key not in st.session_state:
                        st.session_state[select_all_key] = True
                    
                    select_all = st.checkbox(
                        "**Select All / Deselect All**",
                        value=st.session_state[select_all_key],
                        key=select_all_key
                    )
                    
                    st.write("---")
                    
                    # Create checkboxes for each design code
                    selected_codes = []
                    for code, count in sorted_design_codes:
                        # Initialize individual checkbox state if not exists
                        code_key = f"code_{code}_{checkbox_key_suffix}"
                        if code_key not in st.session_state:
                            st.session_state[code_key] = True
                        
                        # Sync with select_all if it just changed
                        if select_all != st.session_state.get(f"{select_all_key}_prev", True):
                            st.session_state[code_key] = select_all
                        
                        # Get description for the design code and truncate for display
                        checkbox_label = f"{code} ({count})"
                        help_text = code
                        if design_code_desc_df is not None:
                            desc_row = design_code_desc_df[design_code_desc_df['design_code'] == code]
                            if not desc_row.empty:
                                description = desc_row.iloc[0]['design_code_description']
                                # Truncate description to ~30 chars for label
                                truncated_desc = description[:30] + "..." if len(description) > 30 else description
                                checkbox_label = f"{truncated_desc} ({count})"
                                help_text = f"{code}: {description}"
                        
                        is_selected = st.checkbox(
                            checkbox_label,
                            value=st.session_state[code_key],
                            key=code_key,
                            help=help_text
                        )
                        if is_selected:
                            selected_codes.append(code)
                    
                    # Store the previous select_all state for next comparison
                    st.session_state[f"{select_all_key}_prev"] = select_all
                else:
                    st.write("No design codes found")
            
            # Filter marks based on selected design codes
            if selected_codes:
                filtered_marks = [
                    mark for mark in result["similar_marks"]
                    if any(code in mark.get("design_codes", []) for code in selected_codes)
                ]
            else:
                filtered_marks = []
            
            with main_col:
                if filtered_marks:
                    st.write(f"Showing {len(filtered_marks)} of {len(result['similar_marks'])} marks")
                    
                    # Cache PDF generation by tracking filtered marks
                    if 'cached_pdf_marks' not in st.session_state:
                        st.session_state.cached_pdf_marks = None
                        st.session_state.cached_pdf_data = None
                    
                    # Get hashable representation of current filtered marks
                    current_marks_hash = tuple(mark.get('serial_no') for mark in filtered_marks)
                    
                    # Generate PDF only if filtered marks have changed
                    if cropped_img is not None:
                        if st.session_state.cached_pdf_marks != current_marks_hash:
                            st.session_state.cached_pdf_data = generate_pdf_report(
                                cropped_img, 
                                filtered_marks, 
                                st.session_state.search_type_used
                            )
                            st.session_state.cached_pdf_marks = current_marks_hash
                        
                        st.download_button(
                            label="📥 Download Results as PDF",
                            data=st.session_state.cached_pdf_data,
                            file_name="trademark_similarity_results.pdf",
                            mime="application/pdf",
                            key="download_pdf_button"
                        )
                    
                    # Create columns for cards layout
                    cols = st.columns(3)  # 3 cards per row
                    
                    for idx, mark in enumerate(filtered_marks):
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
                                serial_no = mark.get('serial_no', 'N/A')
                                st.markdown(f"**Serial No:** [{serial_no}](https://tsdr.uspto.gov/#caseNumber={serial_no}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch)")
                                st.write(f"**Filing Date:** {mark.get('filing_dt', 'N/A')}")
                                st.write(f"**Mark ID:** {mark.get('mark_id_char', 'N/A') or 'N/A'}")
                                st.write(f"**Similarity Score:** {mark.get('similarity_score', 0):.4f}")
                else:
                    st.info("No marks match the selected design codes. Please select at least one design code.")
        else:
            st.info("No similar marks found.")

# ===== WORD MARK SIMILARITY PAGE =====
elif page == "Word Mark Similarity":
    st.title("Word Mark Similarity Search")
    
    # Initialize session state for search results
    if 'word_mark_results' not in st.session_state:
        st.session_state.word_mark_results = None
    
    # Input fields
    st.subheader("Enter Search Parameters")
    
    query_word_mark = st.text_input(
        "Query Word Mark:",
        placeholder="Enter the word mark to search for (e.g., GOOGLE)",
        key="query_word_mark_input"
    )
    
    gs_description = st.text_area(
        "Goods and Services Description:",
        placeholder="Describe the goods and services (eg. software for online search and advertising)",
        height=100,
        key="gs_description_input"
    )
    
    nice_class = st.text_input(
        "NICE Class (Optional):",
        placeholder="Enter NICE class number (e.g., 25)",
        key="nice_class_input"
    )
    
    # Search button
    if st.button("Search", key="word_mark_search_button"):
        if query_word_mark.strip() and gs_description.strip():
            with st.spinner("Searching for similar word marks..."):
                try:
                    # Prepare request body
                    body = {
                        "word_mark": query_word_mark.strip(),
                        "gs_description": gs_description.strip()
                    }
                    
                    # Only include nice_class if provided
                    if nice_class.strip():
                        body["nice_class"] = nice_class.strip()
                    
                    # Make API call
                    response = requests.post(
                        f"{SIMILARITY_SVC_URL}/wmark-app/locCandidatesForWordMark",
                        json=body
                    )
                    
                    if response.status_code == 200:
                        results = response.json()
                        if results and len(results) > 0:
                            st.success(f"Found {len(results)} similar word marks!")
                            st.session_state.word_mark_results = results
                        else:
                            st.info("No similar word marks found.")
                            st.session_state.word_mark_results = None
                    else:
                        st.error(f"Error: {response.status_code} - {response.text}")
                        st.session_state.word_mark_results = None
                        
                except Exception as e:
                    st.error(f"An error occurred: {str(e)}")
                    st.session_state.word_mark_results = None
        else:
            st.warning("Please enter both Query Word Mark and Goods and Services Description.")
    
    # Display results if they exist
    if st.session_state.word_mark_results is not None:
        results = st.session_state.word_mark_results
        
        st.write("---")
        st.subheader("Similarity Analysis")
        
        # Prepare data for scatter plot
        df = pd.DataFrame(results)
        
        # Create hover text combining registration_no and mark_id_char
        df['hover_text'] = df.apply(
            lambda row: f"Registration No: {row['registration_no']}<br>Mark: {row['mark_id_char']}", 
            axis=1
        )
        
        # Create scatter plot
        fig = px.scatter(
            df,
            x='good_services_similarity_score',
            y='word_similarity_score',
            hover_data={'hover_text': True, 
                       'good_services_similarity_score': False, 
                       'word_similarity_score': False,
                       'registration_no': False,
                       'mark_id_char': False},
            labels={
                'good_services_similarity_score': 'Goods & Services Similarity Score',
                'word_similarity_score': 'Word Similarity Score'
            },
            title='Word Mark Similarity Analysis',
            color='word_similarity_score',
            color_continuous_scale='Viridis',
            size_max=10
        )
        
        # Update hover template to only show custom hover text
        fig.update_traces(
            hovertemplate='%{customdata[0]}<extra></extra>'
        )
        
        # Update layout
        fig.update_layout(
            width=900,
            height=600,
            xaxis_title="Goods & Services Similarity Score",
            yaxis_title="Word Similarity Score",
            hovermode='closest'
        )
        
        st.plotly_chart(fig, use_container_width=True)
        
        # Display data table
        with st.expander("📊 View Detailed Results"):
            # Get original serial_no values for display
            serial_nos_display = df['serial_no'].astype(str)
            
            # Create dataframe
            display_df = df[['serial_no', 'registration_no', 'mark_id_char', 'word_similarity_score', 'good_services_similarity_score']].copy()
            
            # Create URLs for Serial No
            display_df['serial_no'] = serial_nos_display.apply(
                lambda x: f"https://tsdr.uspto.gov/#caseNumber={x}&caseSearchType=US_APPLICATION&caseType=DEFAULT&searchType=statusSearch"
            )
            
            # Rename columns
            display_df.columns = ['Serial No', 'Registration No', 'Mark', 'Word Similarity Score', 'G&S Similarity Score']
            
            # Display with LinkColumn and st.dataframe native sorting/filtering
            st.dataframe(
                display_df,
                column_config={
                    "Serial No": st.column_config.LinkColumn(
                        "Serial No",
                        display_text=r"caseNumber=(\d+)"
                    )
                },
                use_container_width=True
            )
            
# ===== COORDINATE CLASS CALCULATOR PAGE =====
elif page == "Coordinate Class Calculator":
    st.title("Coordinate Class Calculator")
    
    if cc_analysis_df is not None:
        st.write("### Class Co-occurrence Probability Heatmap")
        st.write("This heatmap shows P(B|A): Probability that an applicant will file for Class B given they have filed for Class A. For ex: P(25 | 10) would give the probability that an applicant who has filed for Class 10 will also file for Class 25. Use this to identify potential coordinated classes based on historical filing patterns.")
        
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
# import azure.durable_functions as df
# import logging
# import base64
# import json
# import fitz  # PyMuPDF
# from pipelineUtils.blob_functions import get_blob_content

# name = "convertPdfToImages"
# bp = df.Blueprint()

# def normalize_blob_name(container: str, raw_name: str) -> str:
#     """Strip container prefix if included in the name."""
#     if raw_name.startswith(container + "/"):
#         return raw_name[len(container) + 1:]
#     return raw_name

# @bp.function_name(name)
# @bp.activity_trigger(input_name="blobObj")
# def convert_pdf_to_images(blobObj: dict):
#     """
#     Converts a PDF blob to a list of base64-encoded PNG images (one per page).
    
#     Args:
#         blobObj (dict): Dictionary containing 'name', 'container', and 'url' keys
        
#     Returns:
#         list: List of base64-encoded image strings
#     """
#     logging.info(f"[convertPdfToImages] raw input type={type(blobObj)} preview={repr(blobObj)[:200]}")

#     # Handle string input (JSON)
#     if isinstance(blobObj, str):
#         try:
#             blobObj = json.loads(blobObj)
#         except Exception as e:
#             raise TypeError(f"convertPdfToImages expected dict or JSON string; got str that failed JSON decode: {e}")
    
#     if not isinstance(blobObj, dict):
#         raise TypeError(f"convertPdfToImages expected dict; got {type(blobObj)}")

#     try:
#         # Normalize blob name (remove container prefix if present)
#         blob_name = normalize_blob_name(blobObj["container"], blobObj["name"])
#         logging.info(f"Normalized Blob Name: {blob_name}")
        
#         # Get PDF content from blob storage
#         blob_bytes = get_blob_content(
#             container_name=blobObj["container"],
#             blob_path=blob_name
#         )
#         logging.info(f"Retrieved PDF blob, size: {len(blob_bytes)} bytes")

#         # Convert PDF to images using PyMuPDF
#         base64_images = []
#         with fitz.open(stream=blob_bytes, filetype='pdf') as doc:
#             logging.info(f"PDF has {len(doc)} pages")
            
#             for page_num, page in enumerate(doc):
#                 # Render page to pixmap (image)
#                 pix = page.get_pixmap()
                
#                 # Convert pixmap to PNG bytes
#                 img_bytes = pix.tobytes("png")
                
#                 # Encode to base64
#                 b64 = base64.b64encode(img_bytes).decode("utf-8")
#                 base64_images.append(b64)
                
#                 logging.info(f"Converted page {page_num + 1}/{len(doc)} to image (size: {len(img_bytes)} bytes)")
        
#         logging.info(f"Successfully converted PDF to {len(base64_images)} images")
#         return base64_images
        
#     except Exception as e:
#         logging.error(f"Error processing PDF {blobObj}: {e}")
#         raise

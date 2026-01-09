import azure.functions as func
import azure.durable_functions as df

from azure.ai.documentintelligence import DocumentIntelligenceClient
from azure.ai.documentintelligence.models import AnalyzeResult, AnalyzeDocumentRequest

# Import all activities
from activities import getBlobContent, runDocIntel, callAoai, writeToBlob
from activities import convertPdfToImages, callAoaiVision  # New vision-based activities
from configuration import Configuration

from pipelineUtils.prompts import load_prompts
from pipelineUtils.blob_functions import get_blob_content, write_to_blob, BlobMetadata
from pipelineUtils.azure_openai import run_prompt

config = Configuration()

NEXT_STAGE = config.get_value("NEXT_STAGE")

app = df.DFApp(http_auth_level=func.AuthLevel.ANONYMOUS)

import logging

# Event Grid-triggered starter for blob events
# For Flex Consumption plan, this uses Event Grid trigger instead of blob trigger
# The Event Grid subscription is configured in infra/main.bicep
@app.function_name(name="start_orchestrator_on_blob")
@app.event_grid_trigger(arg_name="event")  # ← CHANGE 1
@app.durable_client_input(client_name="client")
async def start_orchestrator_blob(
    event: func.EventGridEvent,     # ← CHANGE 2
    client: df.DurableOrchestrationClient,
):
    # ← CHANGE 3: Parse blob information from Event Grid event
    event_data = event.get_json()
    blob_url = event_data.get('url')
    blob_subject = event.subject  # e.g., /blobServices/default/containers/bronze/blobs/file.pdf
    time_stamp = event.event_time
    
    logging.info(f"Event Grid Event Received")
    logging.info(f"Event Type: {event.event_type}")
    logging.info(f"Subject: {blob_subject}")
    logging.info(f"Blob URL: {blob_url}")
    logging.info(f"Event Time: {time_stamp}")
    
    # ← CHANGE 4: Extract blob name from subject (format: /blobServices/default/containers/{container}/blobs/{name})
    subject_parts = blob_subject.split('/blobs/')
    blob_name = subject_parts[1] if len(subject_parts) > 1 else blob_subject
    # Result: "file.pdf"
    
    # ← CHANGE 5: Extract container name from subject
    container_parts = blob_subject.split('/containers/')
    if len(container_parts) > 1:
        container_name = container_parts[1].split('/')[0]
    else:
        container_name = "bronze"  # default
    # Result: "bronze"
    
    # ← CHANGE 6: Build blob metadata including the container prefix for full path
    full_blob_name = f"{container_name}/{blob_name}"
    # Result: "bronze/file.pdf"
    
    # ← CHANGE 7: Create BlobMetadata (same format as before)
    blob_metadata = BlobMetadata(
        name=full_blob_name,     # e.g. 'bronze/file.pdf'
        url=blob_url,            # full blob URL
        container=container_name,
        time_stamp=time_stamp.isoformat()
    )
    logging.info(f"Blob Metadata: {blob_metadata}")
    logging.info(f"Blob Metadata JSON: {blob_metadata.to_dict()}")

    # Start orchestration (same as before)
    instance_id = await client.start_new("orchestrator", client_input=[blob_metadata.to_dict()])
    logging.info(f"Started orchestration {instance_id} for blob {blob_name}")


# An HTTP-triggered function with a Durable Functions client binding
@app.route(route="client")
@app.durable_client_input(client_name="client")
async def start_orchestrator_http(req: func.HttpRequest, client):
  """
  Starts a new orchestration instance and returns a response to the client.

  args:
    req (func.HttpRequest): The HTTP request object. Contains an array of JSONs with fields: name, url, and container
    client (DurableOrchestrationClient): The Durable Functions client.
  response:
    func.HttpResponse: The HTTP response object.
  """
  
  #Perform basic validation on the request body
  try:
      body = req.get_json()
  except ValueError:
      return func.HttpResponse("Invalid JSON.", status_code=400)

  blobs = body.get("blobs")
  if not isinstance(blobs, list) or not blobs:
      return func.HttpResponse("Invalid request: 'blobs' must be a non-empty array.", status_code=400)

  required = ("name", "url", "container")
  for i, b in enumerate(blobs):
      if not isinstance(b, dict):
          return func.HttpResponse(f"Invalid request: blobs[{i}] must be an object.", status_code=400)
      if any(k not in b or not isinstance(b[k], str) or not b[k].strip() for k in required):
          return func.HttpResponse(f"Invalid request: blobs[{i}] must contain non-empty string keys {required}.", status_code=400)
  
  #invoke the orchestrator function with the list of blobs
  instance_id = await client.start_new('orchestrator', client_input=blobs)
  logging.info(f"Started orchestration with Batch ID = '{instance_id}'.")

  response = client.create_check_status_response(req, instance_id)
  return response

# Orchestrator
@app.function_name(name="orchestrator")
@app.orchestration_trigger(context_name="context")
def run(context):
  input_data = context.get_input()
  logging.info(f"Context {context}")
  logging.info(f"Input data: {input_data}")
  
  sub_tasks = []

  # Create sub-orchestrator for each blob
  for blob_metadata in input_data:
    logging.info(f"Calling sub orchestrator for blob: {blob_metadata}")
    sub_tasks.append(context.call_sub_orchestrator("ProcessBlob", blob_metadata))

  logging.info(f"Sub tasks: {sub_tasks}")

  # Runs a list of asynchronous tasks in parallel and waits for all of them to complete. In this case, the tasks are sub-orchestrations that process each blob_metadata in parallel
  results = yield context.task_all(sub_tasks)
  logging.info(f"Results: {results}")
  return results

#Sub orchestrator
@app.function_name(name="ProcessBlob")
@app.orchestration_trigger(context_name="context")
def process_blob(context):
  blob_metadata = context.get_input()
  sub_orchestration_id = context.instance_id 
  logging.info(f"Process Blob sub Orchestration - Processing blob_metadata: {blob_metadata} with sub orchestration id: {sub_orchestration_id}")
  
  # ====================================================================
  # NEW WORKFLOW: PDF to Images + Vision-based extraction
  # ====================================================================
  
  # Step 1: Convert PDF to base64 images (one image per page)
  base64_images = yield context.call_activity("convertPdfToImages", blob_metadata)
  logging.info(f"Converted PDF to {len(base64_images)} images")
  
  # Step 2: Call Azure OpenAI with vision capabilities to analyze the images
  call_aoai_vision_input = {
      "base64_images": base64_images,
      "instance_id": sub_orchestration_id,
      "blob_metadata": blob_metadata,
      "upload_timestamp": blob_metadata.get("time_stamp")  # Pass the blob upload time
  }
  
  json_str = yield context.call_activity("callAoaiVision", call_aoai_vision_input)
  
  # ====================================================================
  # OLD WORKFLOW: Document Intelligence-based extraction (COMMENTED OUT)
  # ====================================================================
  # # Step 1: Extract text using Document Intelligence
  # text_result = yield context.call_activity("runDocIntel", blob_metadata)
  # 
  # # Step 2: Call Azure OpenAI with extracted text
  # call_aoai_input = {
  #     "text_result": text_result,
  #     "instance_id": sub_orchestration_id 
  # }
  # 
  # json_str = yield context.call_activity("callAoai", call_aoai_input)
  # ====================================================================
  
  # Step 3: Write the extracted JSON to the silver container (same for both workflows)
  task_result = yield context.call_activity(
      "writeToBlob", 
      {
          "json_str": json_str, 
          "blob_name": blob_metadata["name"]
      }

      
  )
  
  # ====================================================================
  # GOLD LAYER: JSON Extraction for 1099-CONSOLIDATED documents
  # ====================================================================
  # Step 4: Check if document is 1099-CONSOLIDATED and extract detailed JSON
  gold_result = None
  try:
      # Parse the classification result to check document type
      import json
      classification_data = json.loads(json_str)
      document_type = classification_data.get('document_type', '')
      
      if document_type == "1099-CONSOLIDATED":
          logging.info(f"Detected 1099-CONSOLIDATED. Extracting detailed JSON for: {blob_metadata['name']}")
          
          # Step 5: Call vision model with detailed JSON extraction prompt
          gold_extract_input = {
              "base64_images": base64_images,
              "instance_id": sub_orchestration_id,
              "prompt_file": "prompts-xml-extraction.yaml",
              "output_format": "json",
              "upload_timestamp": blob_metadata.get("time_stamp")  # Pass the blob upload time
          }
          
          gold_json_str = yield context.call_activity("callAoaiVision", gold_extract_input)
          
          # Step 6: Write detailed JSON to gold container
          gold_result = yield context.call_activity(
              "writeToBlob",
              {
                  "json_str": gold_json_str,
                  "blob_name": blob_metadata["name"],
                  "output_format": "json",
                  "container": "gold"
              }
          )
          logging.info(f"Gold layer JSON extraction completed: {gold_result}")
      else:
          logging.info(f"Document type '{document_type}' is not 1099-CONSOLIDATED. Skipping gold layer extraction.")
  except Exception as e:
      logging.error(f"Error during gold layer processing: {e}")
      gold_result = {"success": False, "error": str(e)}
  
  return {
      "blob": blob_metadata,
      "image_count": len(base64_images),  # Number of PDF pages processed
      "task_result": task_result,
      "gold_extraction": gold_result
  }   

app.register_functions(getBlobContent.bp)
# app.register_functions(runDocIntel.bp)  # COMMENTED OUT - Using vision-based extraction instead
# app.register_functions(callAoai.bp)      # COMMENTED OUT - Using callAoaiVision instead
app.register_functions(writeToBlob.bp)
app.register_functions(convertPdfToImages.bp)  # NEW - PDF to images conversion
app.register_functions(callAoaiVision.bp)      # NEW - Vision-based extraction
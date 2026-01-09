import azure.durable_functions as df
import logging
from pipelineUtils.prompts import load_prompts, load_prompts_from_blob
from pipelineUtils.azure_openai import run_prompt_with_images
import json
from datetime import datetime, timezone

name = "callAoaiVision"
bp = df.Blueprint()

@bp.function_name(name)
@bp.activity_trigger(input_name="inputData")
def run(inputData: dict):
    """
    Calls the Azure OpenAI service with vision capabilities to analyze PDF images.
    
    Args:
        inputData (dict): Dictionary containing:
            - base64_images (list): List of base64-encoded images from PDF pages
            - instance_id (str): Pipeline instance ID for logging
            - prompt_file (optional): Custom prompt file for specific extraction (e.g., XML)
            - output_format (optional): 'json' (default) or 'xml'
    
    Returns:
        str: The JSON or XML response from the Azure OpenAI service
    """
    try:
        # Extract input data
        base64_images = inputData.get('base64_images')
        instance_id = inputData.get('instance_id')
        prompt_file = inputData.get('prompt_file')
        output_format = inputData.get('output_format', 'json')
        blob_metadata = inputData.get('blob_metadata', {})
        
        if not base64_images:
            raise ValueError("No images provided in inputData")
        
        # Extract source filename from blob metadata and strip container prefix
        source_filename = blob_metadata.get('name', 'unknown')
        # Remove container prefix if present (e.g., "bronze/W2.pdf" -> "W2.pdf")
        if '/' in source_filename:
            source_filename = source_filename.split('/', 1)[1]
        logging.info(f"callAoaiVision.py: Processing {len(base64_images)} images, format={output_format}, source_file={source_filename}")
        
        # Load the prompt configuration (custom or default)
        if prompt_file:
            logging.info(f"callAoaiVision.py: Using custom prompt file: {prompt_file}")
            prompt_json = load_prompts_from_blob(prompt_file)
        else:
            prompt_json = load_prompts()
        
        # Build the user prompt with source file information
        user_prompt = prompt_json['user_prompt']
        system_prompt = prompt_json['system_prompt']
        
        # Append source file information to the user prompt
        user_prompt = f"{user_prompt}\n\nIMPORTANT: The source file for these images is: {source_filename}\nYou MUST use this exact filename in the 'source_file' field of the metadata output."
        
        logging.info(f"callAoaiVision.py: User prompt: {user_prompt}")
        logging.info(f"callAoaiVision.py: System prompt: {system_prompt}")
        
        # Call the Azure OpenAI service with vision capabilities
        response_content = run_prompt_with_images(
            instance_id, 
            system_prompt, 
            user_prompt,
            base64_images
        )
        
        # Clean up the response - always expecting JSON format
        if response_content.startswith('```json') and response_content.endswith('```'):
            response_content = response_content.strip('`')
            response_content = response_content.replace('json', '', 1).strip()
        elif response_content.startswith('```') and response_content.endswith('```'):
            response_content = response_content.strip('`').strip()
        
        # Get the upload timestamp from inputData (from event.event_time)
        upload_timestamp = inputData.get('upload_timestamp')
        
        # If upload_timestamp is not available, fall back to current time
        if not upload_timestamp:
            upload_timestamp = datetime.now(timezone.utc).isoformat()
            logging.warning(f"callAoaiVision.py: No upload_timestamp provided, using current time")
        
        logging.info(f"callAoaiVision.py: Using timestamp: {upload_timestamp}")
        
        # Handle multiple JSON objects separated by newlines (common AI response format)
        try:
            # First, try to parse as a single JSON object or array
            parsed_response = json.loads(response_content)
            
            # Handle both single document and array of documents
            if isinstance(parsed_response, list):
                # Multiple documents in array
                for doc in parsed_response:
                    if isinstance(doc, dict) and 'metadata' in doc:
                        doc['metadata']['classification_timestamp'] = upload_timestamp
                logging.info(f"callAoaiVision.py: Updated {len(parsed_response)} documents with timestamp {upload_timestamp}")
            elif isinstance(parsed_response, dict):
                # Single document
                if 'metadata' in parsed_response:
                    parsed_response['metadata']['classification_timestamp'] = upload_timestamp
                    logging.info(f"callAoaiVision.py: Updated single document with timestamp {upload_timestamp}")
            
            # Convert back to JSON string
            response_content = json.dumps(parsed_response, indent=2)
            
        except json.JSONDecodeError as e:
            # If single parse fails, try parsing multiple JSON objects separated by newlines
            logging.info(f"callAoaiVision.py: Single JSON parse failed, trying multi-object parse")
            try:
                lines = response_content.strip().split('\n')
                json_objects = []
                current_obj = ""
                brace_count = 0
                
                for line in lines:
                    current_obj += line + "\n"
                    brace_count += line.count('{') - line.count('}')
                    
                    # When braces are balanced, we have a complete JSON object
                    if brace_count == 0 and current_obj.strip():
                        try:
                            obj = json.loads(current_obj)
                            if isinstance(obj, dict) and 'metadata' in obj:
                                obj['metadata']['classification_timestamp'] = upload_timestamp
                            json_objects.append(obj)
                            current_obj = ""
                        except json.JSONDecodeError:
                            continue
                
                if json_objects:
                    logging.info(f"callAoaiVision.py: Updated {len(json_objects)} documents with timestamp {upload_timestamp}")
                    response_content = '\n'.join([json.dumps(obj, indent=2) for obj in json_objects])
                else:
                    logging.warning(f"callAoaiVision.py: Could not parse response as JSON: {e}")
                    
            except Exception as parse_error:
                logging.error(f"callAoaiVision.py: Error parsing multi-object JSON: {parse_error}")
        
        # Return the response
        return response_content
    
    except Exception as e:
        logging.error(f"Error processing Sub Orchestration (callAoaiVision) {instance_id}: {e}")
        raise

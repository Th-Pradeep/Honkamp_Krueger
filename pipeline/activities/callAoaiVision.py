import azure.durable_functions as df
import logging
from pipelineUtils.prompts import load_prompts, load_prompts_from_blob
from pipelineUtils.azure_openai import run_prompt_with_images
import json

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
        
        # Validate that it's proper JSON
        try:
            json.loads(response_content)
            logging.info(f"callAoaiVision.py: Successfully parsed JSON response")
        except json.JSONDecodeError as e:
            logging.warning(f"callAoaiVision.py: Response is not valid JSON: {e}")
        
        # Return the response
        return response_content
    
    except Exception as e:
        logging.error(f"Error processing Sub Orchestration (callAoaiVision) {instance_id}: {e}")
        raise

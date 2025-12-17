from openai import AzureOpenAI
import os 
import logging
from azure.identity import DefaultAzureCredential, get_bearer_token_provider
from pipelineUtils.db import save_chat_message
from configuration import Configuration
config = Configuration()

OPENAI_API_KEY = config.get_value("OPENAI_API_KEY")
OPENAI_API_BASE = config.get_value("OPENAI_API_BASE")
OPENAI_MODEL = config.get_value("OPENAI_MODEL")
OPENAI_API_VERSION = config.get_value("OPENAI_API_VERSION")
OPENAI_API_EMBEDDING_MODEL = config.get_value("OPENAI_API_EMBEDDING_MODEL")

def get_embeddings(text):
    token_provider = get_bearer_token_provider(  
        config.credential,  
        "https://cognitiveservices.azure.com/.default"  
    )  

    token = config.credential.get_token("https://cognitiveservices.azure.com/.default").token
    openai_client = AzureOpenAI(
            azure_ad_token=token,
            api_version = OPENAI_API_VERSION,
            azure_endpoint =OPENAI_API_BASE
            )
    
    embedding = openai_client.embeddings.create(
                 input = text,
                 model= OPENAI_API_EMBEDDING_MODEL
             ).data[0].embedding
    
    return embedding


def run_prompt(pipeline_id, system_prompt, user_prompt):
    token_provider = get_bearer_token_provider(  
        config.credential,  
        "https://cognitiveservices.azure.com/.default"  
    )  

    token = config.credential.get_token("https://cognitiveservices.azure.com/.default").token
    
    openai_client = AzureOpenAI(
        azure_ad_token=token,
        api_version = OPENAI_API_VERSION,
        azure_endpoint =OPENAI_API_BASE
    )

    logging.info(f"User Prompt: {user_prompt}")
    logging.info(f"System Prompt: {system_prompt}")

    save_chat_message(pipeline_id, "system", system_prompt)
    save_chat_message(pipeline_id, "user", user_prompt)

    try:
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,
            messages=[{ "role": "system", "content": system_prompt},
                {"role":"user","content":user_prompt}])
        assistant_msg = response.choices[0].message.content
        usage = {
            "prompt_tokens":   response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens":    response.usage.total_tokens,
            "model":           response.model
        }

        # 2) log the assistant’s response + usage
        save_chat_message(pipeline_id, "assistant", assistant_msg, usage)
        return assistant_msg
    
    except Exception as e:
        logging.error(f"Error calling OpenAI API: {e}")
        return None


def run_prompt_with_images(pipeline_id, system_prompt, user_prompt, base64_images):
    """
    Calls Azure OpenAI with vision capabilities (multimodal) to analyze images.
    
    Args:
        pipeline_id (str): Pipeline instance ID for logging
        system_prompt (str): System prompt for the model
        user_prompt (str): User prompt/question about the images
        base64_images (list): List of base64-encoded image strings
        
    Returns:
        str: The assistant's response content
    """
    token_provider = get_bearer_token_provider(  
        config.credential,  
        "https://cognitiveservices.azure.com/.default"  
    )  

    token = config.credential.get_token("https://cognitiveservices.azure.com/.default").token
    
    openai_client = AzureOpenAI(
        azure_ad_token=token,
        api_version=OPENAI_API_VERSION,
        azure_endpoint=OPENAI_API_BASE
    )

    logging.info(f"User Prompt: {user_prompt}")
    logging.info(f"System Prompt: {system_prompt}")
    logging.info(f"Number of images: {len(base64_images)}")

    # Save prompts to conversation history
    save_chat_message(pipeline_id, "system", system_prompt)
    save_chat_message(pipeline_id, "user", f"{user_prompt} [with {len(base64_images)} images]")

    try:
        # Build the content array with text and images
        content_items = [
            {"type": "text", "text": user_prompt}
        ]
        
        # Add each image to the content
        for idx, b64_image in enumerate(base64_images):
            content_items.append({
                "type": "image_url",
                "image_url": {
                    "url": f"data:image/png;base64,{b64_image}"
                }
            })
            logging.info(f"Added image {idx + 1}/{len(base64_images)} to request")

        # Call the multimodal model (GPT-4o with vision)
        response = openai_client.chat.completions.create(
            model=OPENAI_MODEL,  # Should be gpt-4o or gpt-4-vision
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": content_items}
            ],
            max_tokens=8000  # Increase for longer responses
        )
        
        assistant_msg = response.choices[0].message.content
        usage = {
            "prompt_tokens": response.usage.prompt_tokens,
            "completion_tokens": response.usage.completion_tokens,
            "total_tokens": response.usage.total_tokens,
            "model": response.model
        }

        # Log the assistant's response + usage
        save_chat_message(pipeline_id, "assistant", assistant_msg, usage)
        
        logging.info(f"Vision API call successful. Tokens used: {usage['total_tokens']}")
        return assistant_msg
    
    except Exception as e:
        logging.error(f"Error calling OpenAI Vision API: {e}")
        raise

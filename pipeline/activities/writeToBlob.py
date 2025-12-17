import azure.durable_functions as df
import logging
from pipelineUtils.blob_functions import list_blobs, get_blob_content, write_to_blob
import os

from configuration import Configuration
config = Configuration()

NEXT_STAGE = config.get_value("NEXT_STAGE")
logging.info(f"writeToBlob.py: NEXT_STAGE is {NEXT_STAGE}")
name = "writeToBlob"
bp = df.Blueprint()

@bp.function_name(name)
@bp.activity_trigger(input_name="args")
def extract_text_from_blob(args: dict):
  """
  Writes JSON or XML data to blob storage (silver or gold container).
  Args:
      args (dict): A dictionary containing:
          - blob_name: Original blob name
          - json_str (optional): JSON string to write to silver container
          - xml_str (optional): XML string to write to gold container
          - container (optional): Target container override
          - output_format (optional): 'json' or 'xml'
  """
  try:
      sourcefile = os.path.splitext(os.path.basename(args['blob_name']))[0]
      
      # Determine output format and container
      output_format = args.get('output_format', 'json')
      container = args.get('container', NEXT_STAGE)
      
      # Encode JSON to bytes
      json_bytes = args['json_str'].encode('utf-8')
      
      # Determine filename based on container
      if container == 'gold':
          # Gold container: detailed extraction JSON
          output_filename = f"{sourcefile}-1099-consolidated.json"
          logging.info(f"writeToBlob.py: Writing detailed JSON to {container}: {output_filename}")
      else:
          # Silver container: classification JSON
          output_filename = f"{sourcefile}-output.json"
          logging.info(f"writeToBlob.py: Writing classification JSON to {container}: {output_filename}")
      
      # Write to blob storage
      result = write_to_blob(container, output_filename, json_bytes)
      
      if result:
          logging.info(f"writeToBlob.py: Successfully wrote JSON to {container}: {output_filename}")
          return {
              "success": True,
              "blob_name": args['blob_name'],
              "output_blob": output_filename,
              "container": container
          }
      else:
          logging.error(f"writeToBlob.py: Failed to write JSON")
          return {"success": False, "error": "Failed to write output"}
              
  except Exception as e:
      error_msg = f"Error writing output for blob {args['blob_name']}: {str(e)}"
      logging.error(error_msg)
      return {"success": False, "error": error_msg}

# ComfyUI workflows

This folder intentionally contains no machine-specific workflow exports. Export a workflow from your own ComfyUI installation with **Save (API Format)**, then select the JSON file in Lumo.

The workflow must include the image-generation nodes and models available in your ComfyUI setup. In Auto generate mode, set `prompt_node_id` in the selected preset JSON to the positive text-prompt node ID from your workflow. Conversation mode can use automatic detection when the workflow labels its positive prompt node clearly; otherwise enter the node ID in the workflow options.

Do not commit private workflow exports if they contain local paths, personal prompts, custom model names you do not want to publish, or other private values.

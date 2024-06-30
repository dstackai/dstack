#!/bin/bash


# Convert HF Model to TensorRT-LLM 
# This script downloads a Hugging Face model, quantizes and compiles it with TensorRT-LLM,
# and uploads the compiled model to Hugging Face.


###########################################
# Set variables
###########################################

# Compilation parameters
MAX_BATCH_SIZE=4
MAX_INPUT_LEN=1024
MAX_OUTPUT_LEN=512
PRIVATE=False 
DTYPE="float16"  

# Directory paths
LOCAL_MODEL_DIR="./hf_model"
CHECKPOINT_DIR="./trt_checkpoint"
ENGINE_DIR="./trt_engine"

###########################################
# Download HF model
###########################################
python3 <<EOF
from huggingface_hub import snapshot_download
snapshot_download("$HF_MODEL_NAME", local_dir="$LOCAL_MODEL_DIR", max_workers=4)
EOF


###########################################
# Quantize the model
###########################################
python TensorRT-LLM/examples/quantization/quantize.py \
    --model_dir $LOCAL_MODEL_DIR \
    --dtype $DTYPE \
    --qformat int4_awq \
    --awq_block_size 128 \
    --output_dir $CHECKPOINT_DIR

###########################################
# Alternative quantization options
###########################################

# Option 2: Without quantization - Convert HF checkpoint to TensorRT-LLM format
# python3 convert_checkpoint.py --model_dir ./hf_model \
#     --output_dir ./trt_engines \
#     --dtype $DTYPE            


###########################################
# Build TensorRT-LLM engine
###########################################
trtllm-build \
    --checkpoint_dir $CHECKPOINT_DIR \
    --output_dir $ENGINE_DIR \
    --gpt_attention_plugin $DTYPE \
    --gemm_plugin $DTYPE \
    --remove_input_padding enable \
    --context_fmha enable \
    --max_batch_size $MAX_BATCH_SIZE \
    --max_input_len $MAX_INPUT_LEN \
    --max_output_len $MAX_OUTPUT_LEN


###########################################
# Push compiled model to Hugging Face
###########################################
python3 <<EOF
from huggingface_hub import HfApi

api = HfApi()
api.create_repo("$HF_USERNAME/$COMPILED_MODEL_NAME", private=$PRIVATE)
api.upload_folder(
    folder_path="$ENGINE_DIR",
    repo_id="$HF_USERNAME/$COMPILED_MODEL_NAME",
    repo_type="model"
)
print("Model successfully pushed to Hugging Face!")
EOF
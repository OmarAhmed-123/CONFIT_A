"""Direct GPU probe: runs the exact Qwen load path on an A10G and prints the full
result/traceback (torch/CUDA, transformers import, from_pretrained, VRAM, a tiny
inference). Used to diagnose why the Web-endpoint containers keep stopping.

Run:  modal run services/vlm-worker/probe_load_modal.py
"""
import os
import traceback

import modal

app = modal.App("confit-vlm-probe")
image = (
    modal.Image.debian_slim(python_version="3.11")
    .apt_install("libgomp1", "libgl1-mesa-glx", "libglib2.0-0")
    .pip_install(
        "torch", "torchvision", "transformers>=4.50.0", "accelerate>=0.33.0",
        "qwen-vl-utils>=0.0.8", "huggingface_hub>=0.24.0", "Pillow>=10.4.0", "numpy>=1.26.0",
    )
)
vol = modal.Volume.from_name("confit-qwen25vl-weights")


@app.function(gpu="A10G", image=image, volumes={"/weights": vol}, timeout=1500)
def probe():
    os.environ.setdefault("QWEN_VL_WEIGHTS_DIR", "/weights")
    import torch

    print(f"[probe] torch={torch.__version__} cuda_avail={torch.cuda.is_available()} "
          f"dev={torch.cuda.get_device_name(0) if torch.cuda.is_available() else 'cpu'} "
          f"devmem={torch.cuda.get_device_properties(0).total_memory / 1024**3:.1f}GiB", flush=True)
    import transformers

    print(f"[probe] transformers={transformers.__version__}", flush=True)
    try:
        from transformers import AutoProcessor, Qwen2_5_VLForConditionalGeneration
    except Exception:
        print("[probe] IMPORT FAILED:", flush=True)
        traceback.print_exc()
        raise SystemExit(1)
    print("[probe] imports OK; from_pretrained(/weights)...", flush=True)
    try:
        model = Qwen2_5_VLForConditionalGeneration.from_pretrained(
            "/weights", torch_dtype=torch.bfloat16, device_map="auto"
        )
        model.eval()
        proc = AutoProcessor.from_pretrained("/weights")
        print(f"[probe] LOAD OK  VRAM alloc={torch.cuda.memory_allocated() / 1024**3:.2f}GiB "
              f"reserved={torch.cuda.memory_reserved() / 1024**3:.2f}GiB", flush=True)
    except Exception:
        print("[probe] LOAD FAILED:", flush=True)
        traceback.print_exc()
        raise SystemExit(1)

    try:
        from PIL import Image
        from qwen_vl_utils import process_vision_info

        img = Image.new("RGB", (224, 224), (120, 90, 60))
        msgs = [{"role": "user", "content": [
            {"type": "image", "image": img},
            {"type": "text", "text": 'Return STRICT JSON only: {"detected_category": null}'},
        ]}]
        text = proc.apply_chat_template(msgs, tokenize=False, add_generation_prompt=True)
        ii, vi = process_vision_info(msgs)
        inputs = proc(text=[text], images=ii, videos=vi, padding=True, return_tensors="pt").to(model.device)
        in_len = inputs["input_ids"].shape[1]
        with torch.inference_mode():
            out = model.generate(**inputs, max_new_tokens=32, do_sample=False)
        res = proc.batch_decode(out[:, in_len:], skip_special_tokens=True)[0]
        print(f"[probe] INFER OK  output={res!r}  VRAM={torch.cuda.memory_allocated() / 1024**3:.2f}GiB", flush=True)
    except Exception:
        print("[probe] INFER FAILED:", flush=True)
        traceback.print_exc()
        raise SystemExit(1)

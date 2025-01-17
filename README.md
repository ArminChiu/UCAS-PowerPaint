# PowerPaint

## Dataset Format
The default I/O directory is `PowerPaint/data`.
You can place it in any directory, but do remember to claim the input and output paths in the command.

It's best to change the file name of your dataset to a numerical number.
This way, you can process data in an orderly manner based on the index.

- `data`
    - `images`
        - `00001.png`
        
            ⋮
        - `xxxxx.png`
    - `masks`
        - `00001_mask.png`
        
            ⋮
        - `xxxxx_mask.png`
    - `output`
        - `00001_output.png`
        
            ⋮
        - `xxxxx_output.png`

## Get Started

### Clone the Repository
```bash
git clone git@github.com:ArminChiu/PowerPaint.git
```

### Create Virtual Environment with Conda
```bash
conda create --name ppt python=3.9
conda activate ppt
```

### Install Dependencies
```bash
pip install -r requirements/requirements.txt
pip uninstall huggingface_hub
pip install huggingface_hub==0.25.0
```

### Set up Git LFS
```bash
conda install git-lfs
git lfs install
```

### Clone PowerPaint Model
```bash
git lfs clone https://hf-mirror.com/JunhaoZhuang/PowerPaint-v1/ ./checkpoints/ppt-v1
```

### Disable the safety_checker (optional)
/root/miniconda3/envs/ppt/lib/python3.9/site-packages/diffusers/pipelines/stable_diffusion/safety_checker.py

Delete the code below:

```py
86  for idx, has_nsfw_concept in enumerate(has_nsfw_concepts):
87      if has_nsfw_concept:
88          if torch.is_tensor(images) or torch.is_tensor(images[0]):
89              images[idx] = torch.zeros_like(images[idx])  # black image
90          else:
91              images[idx] = np.zeros(images[idx].shape)  # black image
92  
93  if any(has_nsfw_concepts):
94      logger.warning(
95          "Potential NSFW content was detected in one or more images. A black image will be returned instead."
96          " Try again with a different prompt and/or seed."
97      )
```

### AutoDL Academic Resource Acceleration (optional)
```bash
source /etc/network_turbo
```

### Launch the Gradio interface
```bash
python app-gradio.py --share
```

### Launch the terminal interface
```bash
python app.py --start_index <start_index> --end_index <end_index> --task object-removal
```
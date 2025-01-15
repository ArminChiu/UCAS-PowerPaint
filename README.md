# PowerPaint

## Get Started

```bash
# Clone the Repository
git clone git@github.com:ArminChiu/PowerPaint.git

# Create Virtual Environment with Conda
conda create --name ppt python=3.9
conda activate ppt

# Install Dependencies
pip install -r requirements/requirements.txt
```

## Inference

You can launch the Gradio interface for PowerPaint by running the following command:

```bash
# Set up Git LFS
conda install git-lfs
git lfs install

# Clone PowerPaint Model
git lfs clone https://hf-mirror.com/JunhaoZhuang/PowerPaint-v1/ ./checkpoints/ppt-v1

source /etc/network_turbo && python app.py --share
```

For the BrushNet-based PowerPaint, you can run the following command:
```bash
# Clone PowerPaint Model
git lfs clone https://hf-mirror.com/JunhaoZhuang/PowerPaint_v2/ ./checkpoints/ppt-v2

source /etc/network_turbo && python app.py --share --version ppt-v2 --checkpoint_dir checkpoints/ppt-v2

python app.py --input_dir ../test/images --mask_dir ../test/masks --output_dir ./output --start_index 1 --end_index 30 --task object-removal --prompt "" --negative_prompt "" --ddim_steps 50 --scale 7.5 --seed 42 --control_type canny --controlnet_conditioning_scale 0.5
```
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

```bash
# Set up Git LFS
conda install git-lfs
git lfs install

# Clone PowerPaint Model
git lfs clone https://hf-mirror.com/JunhaoZhuang/PowerPaint-v1/ ./checkpoints/ppt-v1

# Launch the Gradio interface
source /etc/network_turbo && python app.py --share

# Or launch the cmd interface
python app.py --start_index 1 --end_index 30 --task object-removal
```
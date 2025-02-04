import argparse
import os
import random

import cv2
import numpy as np
import torch
from controlnet_aux import HEDdetector, OpenposeDetector
from PIL import Image, ImageFilter
from safetensors.torch import load_model
from transformers import CLIPTextModel, DPTFeatureExtractor, DPTForDepthEstimation

from diffusers import UniPCMultistepScheduler
from diffusers.pipelines.controlnet.pipeline_controlnet import ControlNetModel
from powerpaint.models.BrushNet_CA import BrushNetModel
from powerpaint.models.unet_2d_condition import UNet2DConditionModel
from powerpaint.pipelines.pipeline_PowerPaint import StableDiffusionInpaintPipeline as Pipeline
from powerpaint.pipelines.pipeline_PowerPaint_Brushnet_CA import StableDiffusionPowerPaintBrushNetPipeline
from powerpaint.pipelines.pipeline_PowerPaint_ControlNet import (
    StableDiffusionControlNetInpaintPipeline as controlnetPipeline,
)
from powerpaint.utils.utils import TokenizerWrapper, add_tokens
from tqdm import tqdm


torch.set_grad_enabled(False)


def set_seed(seed):
    torch.manual_seed(seed)
    torch.cuda.manual_seed(seed)
    torch.cuda.manual_seed_all(seed)
    np.random.seed(seed)
    random.seed(seed)


def add_task(prompt, negative_prompt, control_type, version):
    pos_prefix = neg_prefix = ""
    if control_type == "object-removal" or control_type == "image-outpainting":
        if version == "ppt-v1":
            pos_prefix = "empty scene blur " + prompt
            neg_prefix = negative_prompt
        promptA = pos_prefix + " P_ctxt"
        promptB = pos_prefix + " P_ctxt"
        negative_promptA = neg_prefix + " P_obj"
        negative_promptB = neg_prefix + " P_obj"
    elif control_type == "shape-guided":
        if version == "ppt-v1":
            pos_prefix = prompt
            neg_prefix = negative_prompt + ", worst quality, low quality, normal quality, bad quality, blurry "
        promptA = pos_prefix + " P_shape"
        promptB = pos_prefix + " P_ctxt"
        negative_promptA = neg_prefix + "P_shape"
        negative_promptB = neg_prefix + "P_ctxt"
    else:
        if version == "ppt-v1":
            pos_prefix = prompt
            neg_prefix = negative_prompt + ", worst quality, low quality, normal quality, bad quality, blurry "
        promptA = pos_prefix + " P_obj"
        promptB = pos_prefix + " P_obj"
        negative_promptA = neg_prefix + "P_obj"
        negative_promptB = neg_prefix + "P_obj"

    return promptA, promptB, negative_promptA, negative_promptB


class PowerPaintController:
    def __init__(self, weight_dtype, checkpoint_dir, local_files_only, version) -> None:
        self.version = version
        self.checkpoint_dir = checkpoint_dir
        self.local_files_only = local_files_only

        # initialize powerpaint pipeline
        if version == "ppt-v1":
            self.pipe = Pipeline.from_pretrained(
                "runwayml/stable-diffusion-inpainting", torch_dtype=weight_dtype, local_files_only=local_files_only
            )
            self.pipe.tokenizer = TokenizerWrapper(
                from_pretrained="runwayml/stable-diffusion-v1-5",
                subfolder="tokenizer",
                revision=None,
                local_files_only=local_files_only,
            )

            # add learned task tokens into the tokenizer
            add_tokens(
                tokenizer=self.pipe.tokenizer,
                text_encoder=self.pipe.text_encoder,
                placeholder_tokens=["P_ctxt", "P_shape", "P_obj"],
                initialize_tokens=["a", "a", "a"],
                num_vectors_per_token=10,
            )

            # loading pre-trained weights
            load_model(self.pipe.unet, os.path.join(checkpoint_dir, "unet/unet.safetensors"))
            load_model(self.pipe.text_encoder, os.path.join(checkpoint_dir, "text_encoder/text_encoder.safetensors"))
            self.pipe = self.pipe.to("cuda")

            # initialize controlnet-related models
            self.depth_estimator = DPTForDepthEstimation.from_pretrained("Intel/dpt-hybrid-midas").to("cuda")
            self.feature_extractor = DPTFeatureExtractor.from_pretrained("Intel/dpt-hybrid-midas")
            self.openpose = OpenposeDetector.from_pretrained("lllyasviel/ControlNet")
            self.hed = HEDdetector.from_pretrained("lllyasviel/ControlNet")

            base_control = ControlNetModel.from_pretrained(
                "lllyasviel/sd-controlnet-canny", torch_dtype=weight_dtype, local_files_only=local_files_only
            )
            self.control_pipe = controlnetPipeline(
                self.pipe.vae,
                self.pipe.text_encoder,
                self.pipe.tokenizer,
                self.pipe.unet,
                base_control,
                self.pipe.scheduler,
                None,
                None,
                False,
            )
            self.control_pipe = self.control_pipe.to("cuda")

            self.current_control = "canny"
            # controlnet_conditioning_scale = 0.8
        else:
            # brushnet-based version
            unet = UNet2DConditionModel.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                subfolder="unet",
                revision=None,
                torch_dtype=weight_dtype,
                local_files_only=local_files_only,
            )
            text_encoder_brushnet = CLIPTextModel.from_pretrained(
                "runwayml/stable-diffusion-v1-5",
                subfolder="text_encoder",
                revision=None,
                torch_dtype=weight_dtype,
                local_files_only=local_files_only,
            )
            brushnet = BrushNetModel.from_unet(unet)
            base_model_path = os.path.join(checkpoint_dir, "realisticVisionV60B1_v51VAE")
            self.pipe = StableDiffusionPowerPaintBrushNetPipeline.from_pretrained(
                base_model_path,
                brushnet=brushnet,
                text_encoder_brushnet=text_encoder_brushnet,
                torch_dtype=weight_dtype,
                low_cpu_mem_usage=False,
                safety_checker=None,
            )
            self.pipe.unet = UNet2DConditionModel.from_pretrained(
                base_model_path,
                subfolder="unet",
                revision=None,
                torch_dtype=weight_dtype,
                local_files_only=local_files_only,
            )
            self.pipe.tokenizer = TokenizerWrapper(
                from_pretrained=base_model_path,
                subfolder="tokenizer",
                revision=None,
                torch_type=weight_dtype,
                local_files_only=local_files_only,
            )

            # add learned task tokens into the tokenizer
            add_tokens(
                tokenizer=self.pipe.tokenizer,
                text_encoder=self.pipe.text_encoder_brushnet,
                placeholder_tokens=["P_ctxt", "P_shape", "P_obj"],
                initialize_tokens=["a", "a", "a"],
                num_vectors_per_token=10,
            )
            load_model(
                self.pipe.brushnet,
                os.path.join(checkpoint_dir, "PowerPaint_Brushnet/diffusion_pytorch_model.safetensors"),
            )

            self.pipe.text_encoder_brushnet.load_state_dict(
                torch.load(os.path.join(checkpoint_dir, "PowerPaint_Brushnet/pytorch_model.bin")), strict=False
            )

            self.pipe.scheduler = UniPCMultistepScheduler.from_config(self.pipe.scheduler.config)

            self.pipe.enable_model_cpu_offload()
            self.pipe = self.pipe.to("cuda")

    def get_depth_map(self, image):
        image = self.feature_extractor(images=image, return_tensors="pt").pixel_values.to("cuda")
        with torch.no_grad(), torch.autocast("cuda"):
            depth_map = self.depth_estimator(image).predicted_depth

        depth_map = torch.nn.functional.interpolate(
            depth_map.unsqueeze(1),
            size=(1024, 1024),
            mode="bicubic",
            align_corners=False,
        )
        depth_min = torch.amin(depth_map, dim=[1, 2, 3], keepdim=True)
        depth_max = torch.amax(depth_map, dim=[1, 2, 3], keepdim=True)
        depth_map = (depth_map - depth_min) / (depth_max - depth_min)
        image = torch.cat([depth_map] * 3, dim=1)

        image = image.permute(0, 2, 3, 1).cpu().numpy()[0]
        image = Image.fromarray((image * 255.0).clip(0, 255).astype(np.uint8))
        return image

    def load_controlnet(self, control_type):
        if self.current_control != control_type:
            if control_type == "canny" or control_type is None:
                self.control_pipe.controlnet = ControlNetModel.from_pretrained(
                    "lllyasviel/sd-controlnet-canny", torch_dtype=weight_dtype, local_files_only=self.local_files_only
                )
            elif control_type == "pose":
                self.control_pipe.controlnet = ControlNetModel.from_pretrained(
                    "lllyasviel/sd-controlnet-openpose",
                    torch_dtype=weight_dtype,
                    local_files_only=self.local_files_only,
                )
            elif control_type == "depth":
                self.control_pipe.controlnet = ControlNetModel.from_pretrained(
                    "lllyasviel/sd-controlnet-depth", torch_dtype=weight_dtype, local_files_only=self.local_files_only
                )
            else:
                self.control_pipe.controlnet = ControlNetModel.from_pretrained(
                    "lllyasviel/sd-controlnet-hed", torch_dtype=weight_dtype, local_files_only=self.local_files_only
                )
            self.control_pipe = self.control_pipe.to("cuda")
            self.current_control = control_type

    def predict(
        self,
        input_image,
        prompt,
        fitting_degree,
        ddim_steps,
        scale,
        seed,
        negative_prompt,
        task,
        vertical_expansion_ratio,
        horizontal_expansion_ratio,
    ):
        size1, size2 = input_image["image"].convert("RGB").size

        if task != "image-outpainting":
            if size1 < size2:
                input_image["image"] = input_image["image"].convert("RGB").resize((640, int(size2 / size1 * 640)))
            else:
                input_image["image"] = input_image["image"].convert("RGB").resize((int(size1 / size2 * 640), 640))
        else:
            if size1 < size2:
                input_image["image"] = input_image["image"].convert("RGB").resize((512, int(size2 / size1 * 512)))
            else:
                input_image["image"] = input_image["image"].convert("RGB").resize((int(size1 / size2 * 512), 512))

        if vertical_expansion_ratio is not None and horizontal_expansion_ratio is not None:
            o_W, o_H = input_image["image"].convert("RGB").size
            c_W = int(horizontal_expansion_ratio * o_W)
            c_H = int(vertical_expansion_ratio * o_H)

            expand_img = np.ones((c_H, c_W, 3), dtype=np.uint8) * 127
            original_img = np.array(input_image["image"])
            expand_img[
                int((c_H - o_H) / 2.0) : int((c_H - o_H) / 2.0) + o_H,
                int((c_W - o_W) / 2.0) : int((c_W - o_W) / 2.0) + o_W,
                :,
            ] = original_img

            blurry_gap = 10

            expand_mask = np.ones((c_H, c_W, 3), dtype=np.uint8) * 255
            if vertical_expansion_ratio == 1 and horizontal_expansion_ratio != 1:
                expand_mask[
                    int((c_H - o_H) / 2.0) : int((c_H - o_H) / 2.0) + o_H,
                    int((c_W - o_W) / 2.0) + blurry_gap : int((c_W - o_W) / 2.0) + o_W - blurry_gap,
                    :,
                ] = 0
            elif vertical_expansion_ratio != 1 and horizontal_expansion_ratio != 1:
                expand_mask[
                    int((c_H - o_H) / 2.0) + blurry_gap : int((c_H - o_H) / 2.0) + o_H - blurry_gap,
                    int((c_W - o_W) / 2.0) + blurry_gap : int((c_W - o_W) / 2.0) + o_W - blurry_gap,
                    :,
                ] = 0
            elif vertical_expansion_ratio != 1 and horizontal_expansion_ratio == 1:
                expand_mask[
                    int((c_H - o_H) / 2.0) + blurry_gap : int((c_H - o_H) / 2.0) + o_H - blurry_gap,
                    int((c_W - o_W) / 2.0) : int((c_W - o_W) / 2.0) + o_W,
                    :,
                ] = 0

            input_image["image"] = Image.fromarray(expand_img)
            input_image["mask"] = Image.fromarray(expand_mask)

        if self.version != "ppt-v1":
            if task == "image-outpainting":
                prompt = prompt + " empty scene"
            if task == "object-removal":
                prompt = prompt + " empty scene blur"
        promptA, promptB, negative_promptA, negative_promptB = add_task(prompt, negative_prompt, task, self.version)

        img = np.array(input_image["image"].convert("RGB"))
        W = int(np.shape(img)[0] - np.shape(img)[0] % 8)
        H = int(np.shape(img)[1] - np.shape(img)[1] % 8)
        input_image["image"] = input_image["image"].resize((H, W))
        input_image["mask"] = input_image["mask"].resize((H, W))
        set_seed(seed)

        if self.version == "ppt-v1":
            # for sd-inpainting based method
            result = self.pipe(
                promptA=promptA,
                promptB=promptB,
                tradoff=fitting_degree,
                tradoff_nag=fitting_degree,
                negative_promptA=negative_promptA,
                negative_promptB=negative_promptB,
                image=input_image["image"].convert("RGB"),
                mask=input_image["mask"].convert("RGB"),
                width=H,
                height=W,
                guidance_scale=scale,
                num_inference_steps=ddim_steps,
            ).images[0]
        else:
            # for brushnet-based method
            np_inpimg = np.array(input_image["image"])
            np_inmask = np.array(input_image["mask"]) / 255.0
            np_inpimg = np_inpimg * (1 - np_inmask)
            input_image["image"] = Image.fromarray(np_inpimg.astype(np.uint8)).convert("RGB")
            result = self.pipe(
                promptA=promptA,
                promptB=promptB,
                promptU=prompt,
                tradoff=fitting_degree,
                tradoff_nag=fitting_degree,
                image=input_image["image"].convert("RGB"),
                mask=input_image["mask"].convert("RGB"),
                num_inference_steps=ddim_steps,
                generator=torch.Generator("cuda").manual_seed(seed),
                brushnet_conditioning_scale=1.0,
                negative_promptA=negative_promptA,
                negative_promptB=negative_promptB,
                negative_promptU=negative_prompt,
                guidance_scale=scale,
                width=H,
                height=W,
            ).images[0]

        mask_np = np.array(input_image["mask"].convert("RGB"))
        red = np.array(result).astype("float") * 1
        red[:, :, 0] = 180.0
        red[:, :, 2] = 0
        red[:, :, 1] = 0
        result_m = np.array(result)
        result_m = Image.fromarray(
            (
                result_m.astype("float") * (1 - mask_np.astype("float") / 512.0)
                + mask_np.astype("float") / 512.0 * red
            ).astype("uint8")
        )
        m_img = input_image["mask"].convert("RGB").filter(ImageFilter.GaussianBlur(radius=3))
        m_img = np.asarray(m_img) / 255.0
        img_np = np.asarray(input_image["image"].convert("RGB")) / 255.0
        ours_np = np.asarray(result) / 255.0
        ours_np = ours_np * m_img + (1 - m_img) * img_np
        dict_res = [input_image["mask"].convert("RGB"), result_m]

        # result_paste = Image.fromarray(np.uint8(ours_np * 255))
        # dict_out = [input_image["image"].convert("RGB"), result_paste]
        dict_out = [result]
        return dict_out, dict_res

    def predict_controlnet(
        self,
        input_image,
        input_control_image,
        control_type,
        prompt,
        ddim_steps,
        scale,
        seed,
        negative_prompt,
        controlnet_conditioning_scale,
    ):
        promptA = prompt + " P_obj"
        promptB = prompt + " P_obj"
        negative_promptA = negative_prompt
        negative_promptB = negative_prompt
        size1, size2 = input_image["image"].convert("RGB").size

        if size1 < size2:
            input_image["image"] = input_image["image"].convert("RGB").resize((640, int(size2 / size1 * 640)))
        else:
            input_image["image"] = input_image["image"].convert("RGB").resize((int(size1 / size2 * 640), 640))
        img = np.array(input_image["image"].convert("RGB"))
        W = int(np.shape(img)[0] - np.shape(img)[0] % 8)
        H = int(np.shape(img)[1] - np.shape(img)[1] % 8)
        input_image["image"] = input_image["image"].resize((H, W))
        input_image["mask"] = input_image["mask"].resize((H, W))

        if control_type != self.current_control:
            self.load_controlnet(control_type)
        controlnet_image = input_control_image
        if control_type == "canny":
            controlnet_image = controlnet_image.resize((H, W))
            controlnet_image = np.array(controlnet_image)
            controlnet_image = cv2.Canny(controlnet_image, 100, 200)
            controlnet_image = controlnet_image[:, :, None]
            controlnet_image = np.concatenate([controlnet_image, controlnet_image, controlnet_image], axis=2)
            controlnet_image = Image.fromarray(controlnet_image)
        elif control_type == "pose":
            controlnet_image = self.openpose(controlnet_image)
        elif control_type == "depth":
            controlnet_image = controlnet_image.resize((H, W))
            controlnet_image = self.get_depth_map(controlnet_image)
        else:
            controlnet_image = self.hed(controlnet_image)

        mask_np = np.array(input_image["mask"].convert("RGB"))
        controlnet_image = controlnet_image.resize((H, W))
        set_seed(seed)
        result = self.control_pipe(
            promptA=promptB,
            promptB=promptA,
            tradoff=1.0,
            tradoff_nag=1.0,
            negative_promptA=negative_promptA,
            negative_promptB=negative_promptB,
            image=input_image["image"].convert("RGB"),
            mask=input_image["mask"].convert("RGB"),
            control_image=controlnet_image,
            width=H,
            height=W,
            guidance_scale=scale,
            controlnet_conditioning_scale=controlnet_conditioning_scale,
            num_inference_steps=ddim_steps,
        ).images[0]
        red = np.array(result).astype("float") * 1
        red[:, :, 0] = 180.0
        red[:, :, 2] = 0
        red[:, :, 1] = 0
        result_m = np.array(result)
        result_m = Image.fromarray(
            (
                result_m.astype("float") * (1 - mask_np.astype("float") / 512.0)
                + mask_np.astype("float") / 512.0 * red
            ).astype("uint8")
        )

        mask_np = np.array(input_image["mask"].convert("RGB"))
        m_img = input_image["mask"].convert("RGB").filter(ImageFilter.GaussianBlur(radius=4))
        m_img = np.asarray(m_img) / 255.0
        img_np = np.asarray(input_image["image"].convert("RGB")) / 255.0
        ours_np = np.asarray(result) / 255.0
        ours_np = ours_np * m_img + (1 - m_img) * img_np
        result_paste = Image.fromarray(np.uint8(ours_np * 255))
        return [input_image["image"].convert("RGB"), result_paste], [controlnet_image, result_m]


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--weight_dtype", type=str, default="float16")
    parser.add_argument("--checkpoint_dir", type=str, default="./checkpoints/ppt-v1")
    parser.add_argument("--version", type=str, default="ppt-v1")
    parser.add_argument("--local_files_only", action="store_true", help="enable it to use cached files without requesting from the hub")
    parser.add_argument("--input_dir", type=str, default="./data/images", help="Directory containing input images")
    parser.add_argument("--mask_dir", type=str, default="./data/masks", help="Directory containing mask images")
    parser.add_argument("--output_dir", type=str, default="./data/output", help="Directory to save the output images")
    parser.add_argument("--start_index", type=int, required=True, help="Start index for image processing")
    parser.add_argument("--end_index", type=int, required=True, help="End index for image processing")
    parser.add_argument("--task", type=str, required=True, choices=["text-guided", "object-removal", "shape-guided", "image-outpainting"], help="Task name")
    parser.add_argument("--prompt", type=str, default="", help="Prompt for the task")
    parser.add_argument("--negative_prompt", type=str, default="", help="Negative prompt for the task")
    parser.add_argument("--ddim_steps", type=int, default=50, help="Number of DDIM steps")
    parser.add_argument("--scale", type=float, default=10, help="Guidance scale")
    parser.add_argument("--seed", type=int, default=40, help="Random seed")
    parser.add_argument("--control_type", type=str, default="canny", choices=["canny", "pose", "depth", "hed"], help="Control type for ControlNet")
    parser.add_argument("--controlnet_conditioning_scale", type=float, default=0.5, help="ControlNet conditioning scale")
    args = parser.parse_args()

    # Initialize the pipeline controller
    weight_dtype = torch.float16 if args.weight_dtype == "float16" else torch.float32
    controller = PowerPaintController(weight_dtype, args.checkpoint_dir, args.local_files_only, args.version)

    # Create output directory if it doesn't exist
    os.makedirs(args.output_dir, exist_ok=True)

    # Process images in the specified range with a progress bar
    for i in tqdm(range(args.start_index, args.end_index + 1), desc="Processing images"):
        input_image_path = os.path.join(args.input_dir, f"{i:05d}.png")
        mask_image_path = os.path.join(args.mask_dir, f"{i:05d}_mask.png")

        if not os.path.exists(input_image_path) or not os.path.exists(mask_image_path):
            print(f"Skipping {i:05d}: Input or mask image not found.")
            continue

        # Load input images
        input_image = {"image": Image.open(input_image_path).convert("RGB"), "mask": Image.open(mask_image_path).convert("RGB")}

        # Perform inference
        if args.task == "text-guided":
            result, _ = controller.predict_controlnet(
                input_image,
                input_image["image"],
                args.control_type,
                args.prompt,
                args.ddim_steps,
                args.scale,
                args.seed,
                args.negative_prompt,
                args.controlnet_conditioning_scale,
            )
        else:
            result, _ = controller.predict(
                input_image,
                args.prompt,
                1.0,  # fitting_degree
                args.ddim_steps,
                args.scale,
                args.seed,
                args.negative_prompt,
                args.task,
                None,  # vertical_expansion_ratio
                None,  # horizontal_expansion_ratio
            )

        # Save the output image
        output_image_path = os.path.join(args.output_dir, f"{i:05d}_output.png")
        result[0].save(output_image_path)
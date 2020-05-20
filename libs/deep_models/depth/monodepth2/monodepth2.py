''''''
'''
@Author: Huangying Zhan (huangying.zhan.work@gmail.com)
@Date: 2020-05-19
@Copyright: Copyright (C) Huangying Zhan 2020. All rights reserved. Please refer to the license file.
@LastEditTime: 2020-05-20
@LastEditors: Huangying Zhan
@Description: This is the interface for Monodepth2 depth network
'''

import numpy as np
import os
import PIL.Image as pil
import sys
import torch
from torchvision import transforms

from .depth_decoder import DepthDecoder
from .layers import disp_to_depth
from .resnet_encoder import ResnetEncoder
from ..deep_depth import DeepDepth


class Monodepth2DepthNet(DeepDepth):
    """This is the interface for Monodepth2 depth network
    """

    def initialize_network_model(self, weight_path, dataset='kitti'):
        """initialize network and load pretrained model
        
        Args:
            weight_path (str): a directory stores the pretrained models.
                - **encoder.pth**: encoder model
                - **depth.pth**: depth decoder model
            dataset (str): dataset setup for min/max depth [kitti, tum]
        """
        device = torch.device("cuda")

        # initilize network
        self.encoder = ResnetEncoder(18, False)
        self.depth_decoder = DepthDecoder(
                num_ch_enc=self.encoder.num_ch_enc, scales=range(4))

        print("==> Initialize Depth-CNN with [{}]".format(weight_path))
        # loading pretrained model (encoder)
        encoder_path = os.path.join(weight_path, 'encoder.pth')
        loaded_dict_enc = torch.load(encoder_path, map_location=device)
        filtered_dict_enc = {k: v for k, v in loaded_dict_enc.items() if k in self.encoder.state_dict()}
        self.encoder.load_state_dict(filtered_dict_enc)
        self.encoder.to(device)
        self.encoder.eval()

        # loading pretrained model (depth-decoder)
        depth_decoder_path = os.path.join(weight_path, 'depth.pth')
        loaded_dict = torch.load(depth_decoder_path, map_location=device)
        self.depth_decoder.load_state_dict(loaded_dict)
        self.depth_decoder.to(device)
        self.depth_decoder.eval()

        # image size
        self.feed_height = loaded_dict_enc['height']
        self.feed_width = loaded_dict_enc['width']

        # dataset parameters
        if 'kitti' in dataset:
            self.min_depth = 0.1
            self.max_depth = 100
            self.stereo_baseline = 5.4
        elif 'tum' in dataset:
            self.min_depth = 0.1
            self.max_depth = 10
            self.stereo_baseline = 1
        else:
            self.min_depth = 0.1
            self.max_depth = 100
            self.stereo_baseline = 5.4

    @torch.no_grad()
    def inference(self, img):
        """Depth prediction

        Args:
            img (array, [HxWx3]): image array

        Returns:
            depth (array, [HxW]): depth map
        """
        device = torch.device('cuda')
        feed_width = self.feed_width
        feed_height = self.feed_height

        # Preprocess
        input_image = pil.fromarray(img)
        original_width, original_height = input_image.size
        input_image = input_image.resize((feed_width, feed_height), pil.LANCZOS)
        input_image = transforms.ToTensor()(input_image).unsqueeze(0)

        # Prediction
        input_image = input_image.to(device)
        features = self.encoder(input_image)
        outputs = self.depth_decoder(features)

        disp = outputs[('disp', 0)]
        disp_resized = torch.nn.functional.interpolate(
            disp, (original_height, original_width), mode='bilinear', align_corners=False)

        scaled_disp, _ = disp_to_depth(disp_resized, self.min_depth, self.max_depth)
        depth = self.stereo_baseline / scaled_disp
        depth = depth.detach().cpu().numpy()[0, 0]
        return depth
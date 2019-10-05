"""
Copyright (c) 2019-present NAVER Corp.
MIT License
"""

# -*- coding: utf-8 -*-
import sys
import os
import time
import argparse

import torch
import torch.nn as nn
import torch.backends.cudnn as cudnn
from torch.autograd import Variable

from PIL import Image

import cv2
from skimage import io
import numpy as np
import craft_utils
import imgproc
import file_utils
import json
import zipfile

from craft import CRAFT
from collections import OrderedDict

class TextDetectorWrapper:

    def __init__(self, arguments):
        parser = argparse.ArgumentParser(description='CRAFT Text Detection')
        parser.add_argument('--trained_model', default='weights/craft_mlt_25k.pth', type=str, help='pretrained model')
        parser.add_argument('--text_threshold', default=0.7, type=float, help='text confidence threshold')
        parser.add_argument('--low_text', default=0.4, type=float, help='text low-bound score')
        parser.add_argument('--link_threshold', default=0.4, type=float, help='link confidence threshold')
        parser.add_argument('--cuda', default=True, type=str2bool, help='Use cuda for inference')
        parser.add_argument('--canvas_size', default=1280, type=int, help='image size for inference')
        parser.add_argument('--mag_ratio', default=1.5, type=float, help='image magnification ratio')
        parser.add_argument('--poly', default=False, action='store_true', help='enable polygon type')
        parser.add_argument('--show_time', default=False, action='store_true', help='show processing time')
        parser.add_argument('--test_folder', default='/data/', type=str, help='folder path to input images')
        parser.add_argument('--refine', default=False, action='store_true', help='enable link refiner')
        parser.add_argument('--refiner_model', default='weights/craft_refiner_CTW1500.pth', type=str, help='pretrained refiner model')
        self.args = parser.parse_args(arguments)

        self.result_folder = './result/'
        if not os.path.isdir(self.result_folder):
            os.mkdir(self.result_folder)

        # load net
        self.net = CRAFT()     # initialize

        print('Loading weights from checkpoint (' + self.args.trained_model + ')')
        if self.args.cuda:
            self.net.load_state_dict(self.copyStateDict(torch.load(self.args.trained_model)))
        else:
            self.net.load_state_dict(self.copyStateDict(torch.load(self.args.trained_model, map_location='cpu')))

        if self.args.cuda:
            self.net = self.net.cuda()
            self.net = torch.nn.DataParallel(self.net)
            cudnn.benchmark = False

        self.net.eval()

        # LinkRefiner
        self.refine_net = None
        if self.args.refine:
            from refinenet import RefineNet
            self.refine_net = RefineNet()
            print('Loading weights of refiner from checkpoint (' + self.args.refiner_model + ')')
            if self.args.cuda:
                self.refine_net.load_state_dict(self.copyStateDict(torch.load(self.args.refiner_model)))
                self.refine_net = self.refine_net.cuda()
                self.refine_net = self.torch.nn.DataParallel(self.refine_net)
            else:
                self.refine_net.load_state_dict(self.copyStateDict(torch.load(self.args.refiner_model, map_location='cpu')))

            self.refine_net.eval()
            self.args.poly = True

    def copyStateDict(self, state_dict):
        if list(state_dict.keys())[0].startswith("module"):
            start_idx = 1
        else:
            start_idx = 0
        new_state_dict = OrderedDict()
        for k, v in state_dict.items():
            name = ".".join(k.split(".")[start_idx:])
            new_state_dict[name] = v
        return new_state_dict

    def test_net(self, net, image, text_threshold, link_threshold, low_text, cuda, poly, refine_net=None):
        t0 = time.time()

        # resize
        img_resized, target_ratio, size_heatmap = imgproc.resize_aspect_ratio(image, self.args.canvas_size, interpolation=cv2.INTER_LINEAR, mag_ratio=self.args.mag_ratio)
        ratio_h = ratio_w = 1 / target_ratio

        # preprocessing
        x = imgproc.normalizeMeanVariance(img_resized)
        x = torch.from_numpy(x).permute(2, 0, 1)    # [h, w, c] to [c, h, w]
        x = Variable(x.unsqueeze(0))                # [c, h, w] to [b, c, h, w]
        if cuda:
            x = x.cuda()

        # forward pass
        y, feature = net(x)

        # make score and link map
        score_text = y[0,:,:,0].cpu().data.numpy()
        score_link = y[0,:,:,1].cpu().data.numpy()

        # refine link
        if refine_net is not None:
            y_refiner = refine_net(y, feature)
            score_link = y_refiner[0,:,:,0].cpu().data.numpy()

        t0 = time.time() - t0
        t1 = time.time()

        # Post-processing
        boxes, polys = craft_utils.getDetBoxes(score_text, score_link, text_threshold, link_threshold, low_text, poly)

        # coordinate adjustment
        boxes = craft_utils.adjustResultCoordinates(boxes, ratio_w, ratio_h)
        polys = craft_utils.adjustResultCoordinates(polys, ratio_w, ratio_h)
        for k in range(len(polys)):
            if polys[k] is None: polys[k] = boxes[k]

        t1 = time.time() - t1

        # render results (optional)
        render_img = score_text.copy()
        render_img = np.hstack((render_img, score_link))
        ret_score_text = imgproc.cvt2HeatmapImg(render_img)

        if self.args.show_time : print("\ninfer/postproc time : {:.3f}/{:.3f}".format(t0, t1))

        return boxes, polys, ret_score_text

    def predict(self, image_path):
        image = imgproc.loadImage(image_path)

        bboxes, polys, score_text = self.test_net(self.net, image, self.args.text_threshold, self.args.link_threshold, self.args.low_text, self.args.cuda, self.args.poly, self.refine_net)

        file_utils.saveResult(image_path, image[:,:,::-1], polys, dirname=self.result_folder)


def str2bool(v):
    return v.lower() in ("yes", "y", "true", "t", "1")

if __name__ == '__main__':

    # Initialize model
    arguments = ["--trained_model=./pretrained_models/craft_mlt_25k.pth", "--test_folder=./demo_images", "--cuda=false", "--text_threshold=0.1", "--low_text=0.1", "--link_threshold=0.4"]
    TextDetectorWrapper = TextDetectorWrapper(arguments)

    # Run against test data
    t = time.time()
    image_list, _, _ = file_utils.get_files("./demo_images")
    for k, image_path in enumerate(image_list):
        print("Test image %d/%d: %s" % (k+1, len(image_list), image_path))
        TextDetectorWrapper.predict(image_path)

    print("elapsed time : {}s".format(time.time() - t))
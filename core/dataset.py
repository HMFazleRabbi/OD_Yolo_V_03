#! /usr/bin/env python
# coding=utf-8
#================================================================
#   Copyright (C) 2019 * Ltd. All rights reserved.
#
#   Editor      : VIM
#   File name   : dataset.py
#   Author      : YunYang1994
#   Created date: 2019-03-15 18:05:03
#   Description :
#
#================================================================

import os, glob
import cv2
import random
import numpy as np
import tensorflow.compat.v1 as tf
tf.disable_v2_behavior()
import core.utils as utils
from core.config import cfg

# *************************************************************
#   Author       : HM Fazle Rabbi
#   Description  : Data loader for the yolo. This is the original
#   one from the repo. New dataset aka dataloaders should inherit 
#   from this class. Use cauttion while inheriting. Check to see
#   whether you need to call the parent constructor.
#   Date Modified: 
#   Copyright © 2000, MV Technology Ltd. All rights reserved.
# *************************************************************
class Dataset(object):
    """implement Dataset here"""
    def __init__(self, dataset_type):
        self.annot_path  = cfg.TRAIN.ANNOT_PATH if dataset_type == 'train' else cfg.TEST.ANNOT_PATH
        self.input_sizes = cfg.TRAIN.INPUT_SIZE if dataset_type == 'train' else cfg.TEST.INPUT_SIZE
        self.batch_size  = cfg.TRAIN.BATCH_SIZE if dataset_type == 'train' else cfg.TEST.BATCH_SIZE
        self.data_aug    = cfg.TRAIN.DATA_AUG   if dataset_type == 'train' else cfg.TEST.DATA_AUG

        self.train_input_sizes = cfg.TRAIN.INPUT_SIZE
        self.strides = np.array(cfg.YOLO.STRIDES)
        self.classes = utils.read_class_names(cfg.YOLO.CLASSES)
        self.num_classes = len(self.classes)
        self.channels    = cfg.YOLO.CHANNELS
        self.anchors = np.array(utils.get_anchors(cfg.YOLO.ANCHORS))
        self.anchor_per_scale = cfg.YOLO.ANCHOR_PER_SCALE
        self.max_bbox_per_scale = 150

        self.annotations = self.load_annotations(dataset_type)
        self.num_samples = len(self.annotations)
        self.num_batchs = int(np.ceil(self.num_samples / self.batch_size))
        self.batch_count = 0


    def load_annotations(self, dataset_type):
        with open(self.annot_path, 'r') as f:
            txt = f.readlines()
            annotations = [line.strip() for line in txt if len(line.strip().split()[1:]) != 0]
            # annotations[6] is 'D:/FZ_WS/JyNB/Yolo_LD/tf_yolov3/dataset/VOC\\test/VOCdevkit/VOC2007\\JPEGImages\\000010.jpg 87,97,258,427,12 133,72,245,284,14'
        np.random.shuffle(annotations)
        return annotations

    def __iter__(self):
        return self

    def __next__(self):

        with tf.device('/cpu:0'):
            self.train_input_size = random.choice(self.train_input_sizes)
            self.train_output_sizes = self.train_input_size // self.strides

            batch_image = np.zeros((self.batch_size, self.train_input_size, self.train_input_size, self.channels))

            batch_label_sbbox = np.zeros((self.batch_size, self.train_output_sizes[0], self.train_output_sizes[0],
                                          self.anchor_per_scale, 5 + self.num_classes))
            batch_label_mbbox = np.zeros((self.batch_size, self.train_output_sizes[1], self.train_output_sizes[1],
                                          self.anchor_per_scale, 5 + self.num_classes))
            batch_label_lbbox = np.zeros((self.batch_size, self.train_output_sizes[2], self.train_output_sizes[2],
                                          self.anchor_per_scale, 5 + self.num_classes))

            batch_sbboxes = np.zeros((self.batch_size, self.max_bbox_per_scale, 4))
            batch_mbboxes = np.zeros((self.batch_size, self.max_bbox_per_scale, 4))
            batch_lbboxes = np.zeros((self.batch_size, self.max_bbox_per_scale, 4))

            num = 0
            if self.batch_count < self.num_batchs:
                while num < self.batch_size:
                    index = self.batch_count * self.batch_size + num
                    if index >= self.num_samples: index -= self.num_samples
                    annotation = self.annotations[index]
                    image, bboxes = self.parse_annotation(annotation)
                    label_sbbox, label_mbbox, label_lbbox, sbboxes, mbboxes, lbboxes = self.preprocess_true_boxes(bboxes)

                    batch_image[num, :, :, :] = image
                    batch_label_sbbox[num, :, :, :, :] = label_sbbox
                    batch_label_mbbox[num, :, :, :, :] = label_mbbox
                    batch_label_lbbox[num, :, :, :, :] = label_lbbox
                    batch_sbboxes[num, :, :] = sbboxes
                    batch_mbboxes[num, :, :] = mbboxes
                    batch_lbboxes[num, :, :] = lbboxes
                    num += 1
                self.batch_count += 1
                return batch_image, batch_label_sbbox, batch_label_mbbox, batch_label_lbbox, \
                       batch_sbboxes, batch_mbboxes, batch_lbboxes
            else:
                self.batch_count = 0
                np.random.shuffle(self.annotations)
                raise StopIteration

    def random_horizontal_flip(self, image, bboxes):

        if random.random() < 0.5:
            _, w, _ = image.shape
            image = image[:, ::-1, :]
            bboxes[:, [0,2]] = w - bboxes[:, [2,0]]

        return image, bboxes

    def random_crop(self, image, bboxes):

        if random.random() < 0.5:
            h, w, _ = image.shape
            max_bbox = np.concatenate([np.min(bboxes[:, 0:2], axis=0), np.max(bboxes[:, 2:4], axis=0)], axis=-1)

            max_l_trans = max_bbox[0]
            max_u_trans = max_bbox[1]
            max_r_trans = w - max_bbox[2]
            max_d_trans = h - max_bbox[3]

            crop_xmin = max(0, int(max_bbox[0] - random.uniform(0, max_l_trans)))
            crop_ymin = max(0, int(max_bbox[1] - random.uniform(0, max_u_trans)))
            crop_xmax = max(w, int(max_bbox[2] + random.uniform(0, max_r_trans)))
            crop_ymax = max(h, int(max_bbox[3] + random.uniform(0, max_d_trans)))

            image = image[crop_ymin : crop_ymax, crop_xmin : crop_xmax]

            bboxes[:, [0, 2]] = bboxes[:, [0, 2]] - crop_xmin
            bboxes[:, [1, 3]] = bboxes[:, [1, 3]] - crop_ymin

        return image, bboxes

    def random_translate(self, image, bboxes):

        if random.random() < 0.5:
            h, w, _ = image.shape
            max_bbox = np.concatenate([np.min(bboxes[:, 0:2], axis=0), np.max(bboxes[:, 2:4], axis=0)], axis=-1)

            max_l_trans = max_bbox[0]
            max_u_trans = max_bbox[1]
            max_r_trans = w - max_bbox[2]
            max_d_trans = h - max_bbox[3]

            tx = random.uniform(-(max_l_trans - 1), (max_r_trans - 1))
            ty = random.uniform(-(max_u_trans - 1), (max_d_trans - 1))

            M = np.array([[1, 0, tx], [0, 1, ty]])
            image = cv2.warpAffine(image, M, (w, h))

            bboxes[:, [0, 2]] = bboxes[:, [0, 2]] + tx
            bboxes[:, [1, 3]] = bboxes[:, [1, 3]] + ty

        return image, bboxes

    def parse_annotation(self, annotation):

        line = annotation.split()
        image_path = line[0]
        if not os.path.exists(image_path):
            raise KeyError("%s does not exist ... " %image_path)
        image = np.array(cv2.imread(image_path))
        bboxes = np.array([list(map(lambda x: int(float(x)), box.split(','))) for box in line[1:]])

        if self.data_aug:
            image, bboxes = self.random_horizontal_flip(np.copy(image), np.copy(bboxes))
            image, bboxes = self.random_crop(np.copy(image), np.copy(bboxes))
            image, bboxes = self.random_translate(np.copy(image), np.copy(bboxes))

        image, bboxes = utils.image_preporcess(np.copy(image), [self.train_input_size, self.train_input_size], np.copy(bboxes))
        return image, bboxes

    def bbox_iou(self, boxes1, boxes2):

        boxes1 = np.array(boxes1)
        boxes2 = np.array(boxes2)

        boxes1_area = boxes1[..., 2] * boxes1[..., 3]
        boxes2_area = boxes2[..., 2] * boxes2[..., 3]

        boxes1 = np.concatenate([boxes1[..., :2] - boxes1[..., 2:] * 0.5,
                                boxes1[..., :2] + boxes1[..., 2:] * 0.5], axis=-1)
        boxes2 = np.concatenate([boxes2[..., :2] - boxes2[..., 2:] * 0.5,
                                boxes2[..., :2] + boxes2[..., 2:] * 0.5], axis=-1)

        left_up = np.maximum(boxes1[..., :2], boxes2[..., :2])
        right_down = np.minimum(boxes1[..., 2:], boxes2[..., 2:])

        inter_section = np.maximum(right_down - left_up, 0.0)
        inter_area = inter_section[..., 0] * inter_section[..., 1]
        union_area = boxes1_area + boxes2_area - inter_area

        return inter_area / union_area

    def preprocess_true_boxes(self, bboxes):

        label = [np.zeros((self.train_output_sizes[i], self.train_output_sizes[i], self.anchor_per_scale,
                           5 + self.num_classes)) for i in range(3)]
        bboxes_xywh = [np.zeros((self.max_bbox_per_scale, 4)) for _ in range(3)]
        bbox_count = np.zeros((3,))

        for bbox in bboxes:
            bbox_coor = bbox[:4]
            bbox_class_ind = bbox[4]

            onehot = np.zeros(self.num_classes, dtype=np.float)
            onehot[bbox_class_ind] = 1.0
            uniform_distribution = np.full(self.num_classes, 1.0 / self.num_classes)
            deta = 0.01
            smooth_onehot = onehot * (1 - deta) + deta * uniform_distribution

            bbox_xywh = np.concatenate([(bbox_coor[2:] + bbox_coor[:2]) * 0.5, bbox_coor[2:] - bbox_coor[:2]], axis=-1)
            bbox_xywh_scaled = 1.0 * bbox_xywh[np.newaxis, :] / self.strides[:, np.newaxis]

            iou = []
            exist_positive = False
            for i in range(3):
                anchors_xywh = np.zeros((self.anchor_per_scale, 4))
                anchors_xywh[:, 0:2] = np.floor(bbox_xywh_scaled[i, 0:2]).astype(np.int32) + 0.5
                anchors_xywh[:, 2:4] = self.anchors[i]

                iou_scale = self.bbox_iou(bbox_xywh_scaled[i][np.newaxis, :], anchors_xywh)
                iou.append(iou_scale)
                iou_mask = iou_scale > 0.3

                if np.any(iou_mask):
                    xind, yind = np.floor(bbox_xywh_scaled[i, 0:2]).astype(np.int32)

                    label[i][yind, xind, iou_mask, :] = 0
                    label[i][yind, xind, iou_mask, 0:4] = bbox_xywh
                    label[i][yind, xind, iou_mask, 4:5] = 1.0
                    label[i][yind, xind, iou_mask, 5:] = smooth_onehot

                    bbox_ind = int(bbox_count[i] % self.max_bbox_per_scale)
                    bboxes_xywh[i][bbox_ind, :4] = bbox_xywh
                    bbox_count[i] += 1

                    exist_positive = True

            if not exist_positive:
                best_anchor_ind = np.argmax(np.array(iou).reshape(-1), axis=-1)
                best_detect = int(best_anchor_ind / self.anchor_per_scale)
                best_anchor = int(best_anchor_ind % self.anchor_per_scale)
                xind, yind = np.floor(bbox_xywh_scaled[best_detect, 0:2]).astype(np.int32)

                label[best_detect][yind, xind, best_anchor, :] = 0
                label[best_detect][yind, xind, best_anchor, 0:4] = bbox_xywh
                label[best_detect][yind, xind, best_anchor, 4:5] = 1.0
                label[best_detect][yind, xind, best_anchor, 5:] = smooth_onehot

                bbox_ind = int(bbox_count[best_detect] % self.max_bbox_per_scale)
                bboxes_xywh[best_detect][bbox_ind, :4] = bbox_xywh
                bbox_count[best_detect] += 1
        label_sbbox, label_mbbox, label_lbbox = label
        sbboxes, mbboxes, lbboxes = bboxes_xywh
        return label_sbbox, label_mbbox, label_lbbox, sbboxes, mbboxes, lbboxes

    def __len__(self):
        return self.num_batchs


# *************************************************************
#   Author       : HM Fazle Rabbi
#   Description  : Dataset loader created to support the x1y1x2y2
#   coordinate system and the fetching and loading the RGB image only.
#   Date Modified: 20200318_2313
#   Copyright © 2000, MV Technology Ltd. All rights reserved.
# *************************************************************
class Dataset_LD_RGB (Dataset):
    
    """ Dataloader in vitrox OD supported format """
    def __init__(self, dataset_type):
        self.annot_path  = cfg.TRAIN.ANNOT_PATH if dataset_type == 'train' else cfg.TEST.ANNOT_PATH
        self.input_sizes = cfg.TRAIN.INPUT_SIZE if dataset_type == 'train' else cfg.TEST.INPUT_SIZE
        self.batch_size  = cfg.TRAIN.BATCH_SIZE if dataset_type == 'train' else cfg.TEST.BATCH_SIZE
        self.data_aug    = cfg.TRAIN.DATA_AUG   if dataset_type == 'train' else cfg.TEST.DATA_AUG

        self.train_input_sizes  = cfg.TRAIN.INPUT_SIZE
        self.strides            = np.array(cfg.YOLO.STRIDES)
        self.classes            = utils.read_class_names(cfg.YOLO.CLASSES)
        self.num_classes        = len(self.classes)
        self.channels           = cfg.YOLO.CHANNELS
        self.anchors            = np.array(utils.get_anchors(cfg.YOLO.ANCHORS))
        self.anchor_per_scale   = cfg.YOLO.ANCHOR_PER_SCALE
        self.max_bbox_per_scale = 150

        self.annotations    = self.load_annotations(dataset_type)
        self.num_samples    = len(self.annotations)
        self.num_batchs     = int(np.ceil(self.num_samples / self.batch_size))
        self.batch_count    = 0

    def load_annotations(self, dataset_type):
        pattern = os.path.join(os.path.normpath(self.annot_path), "*.txt")
        txt_flist = glob.glob(pattern)

        annotations=[]
        for fname in txt_flist:
            with open(fname, 'r') as f:
                txt = f.read()
                txt = txt.strip()
                txt = txt.replace("\n", " ")
                txt = fname + ' ' + txt
                if (len(txt.strip().split(',')[1:]) !=0):
                    annotations.append(txt.strip())

        np.random.shuffle(annotations)
        return annotations

    def parse_annotation(self, annotation):

        line = annotation.split()
        image_path = line[0]
        image_path = image_path[:-4] + "_8.jpg"
        if not os.path.exists(image_path):
            raise KeyError("%s does not exist ... " %image_path)
        image = np.array(cv2.imread(image_path))
        bboxes = np.array([list(map(lambda x: int(float(x)), box.split(','))) for box in line[1:]])
       
        
        # Sanity check
        if ((bboxes.min()<0) and (bboxes[:, :-1] !=0)):
            raise KeyError ("Error (parse_annotation(self, annotation)): bboxes.min()<0 ")
        if (bboxes[:,[0,2]].max()>image.shape[1] ):
            raise KeyError("Error (parse_annotation(self, annotation)): bboxes[:,[0,2]].max()>image.shape[1] ")
        if (bboxes[:,[1,3]].max()>image.shape[0] ):
            raise KeyError("Error (parse_annotation(self, annotation)): bboxes[:,[1,3]].max()>image.shape[0] ")

        # Augmentations
        if self.data_aug:
            image, bboxes = self.random_horizontal_flip(np.copy(image), np.copy(bboxes))
            image, bboxes = self.random_crop(np.copy(image), np.copy(bboxes))
            image, bboxes = self.random_translate(np.copy(image), np.copy(bboxes))

        # Preprocessing aka resizing
        image, bboxes = utils.ObjectDetectionUtility.getInstance().image_preporcess(np.copy(image), [self.train_input_size, self.train_input_size], np.copy(bboxes), skip_resize=True)
        
        # Sanity check
        if (bboxes.min()<0):
            if (bboxes_xywh[:,[0,2]].max()>image.shape[1]): 
                print("ERROR: Location exceed image width by",bboxes_xywh[:,2].max()-image.shape[1])
            if (bboxes_xywh[:,[1,3]].max()>image.shape[0] ):
                print("ERROR: Location exceed image height by",bboxes_xywh[:,3].max()-image.shape[0])

            with  open("./data/log/DatabaseParsing_Error.txt", "a")  as myfile:
                myfile.write(annotation.split()[0])
                myfile.write("\n")
            # raise KeyError("Error: Mismatched dimension! ", bboxes_xywh)
            
        return image, bboxes

# *************************************************************
#   Author       : HM Fazle Rabbi
#   Description  : Special dataset created to read ZL database 
#   The reason is the coordinate system it was using is x1y1,w,h
#   and it uses the label "pin"/"lead"
#   Date Modified: 20200318_2320
#   Copyright © 2000, MV Technology Ltd. All rights reserved.
# *************************************************************
class Dataset_LD_ZL (Dataset):

    """ Dataloader in vitrox OD supported format """
    def __init__(self, dataset_type):
        self.annot_path  = cfg.TRAIN.ANNOT_PATH if dataset_type == 'train' else cfg.TEST.ANNOT_PATH
        self.input_sizes = cfg.TRAIN.INPUT_SIZE if dataset_type == 'train' else cfg.TEST.INPUT_SIZE
        self.batch_size  = cfg.TRAIN.BATCH_SIZE if dataset_type == 'train' else cfg.TEST.BATCH_SIZE
        self.data_aug    = cfg.TRAIN.DATA_AUG   if dataset_type == 'train' else cfg.TEST.DATA_AUG

        self.train_input_sizes  = cfg.TRAIN.INPUT_SIZE
        self.strides            = np.array(cfg.YOLO.STRIDES)
        self.classes            = utils.read_class_names(cfg.YOLO.CLASSES)
        self.num_classes        = len(self.classes)
        self.channels           = cfg.YOLO.CHANNELS
        self.anchors            = np.array(utils.get_anchors(cfg.YOLO.ANCHORS))
        self.anchor_per_scale   = cfg.YOLO.ANCHOR_PER_SCALE
        self.max_bbox_per_scale = 150

        self.annotations    = self.load_annotations(dataset_type)
        self.num_samples    = len(self.annotations)
        self.num_batchs     = int(np.ceil(self.num_samples / self.batch_size))
        self.batch_count    = 0

    
    def load_annotations(self, dataset_type):
        pattern = os.path.join(os.path.normpath(self.annot_path), "*.txt")
        txt_flist = glob.glob(pattern)

        annotations=[]
        for fname in txt_flist:
            with open(fname, 'r') as f:
                txt = f.read()
                txt = txt.replace(" ", ",")
                txt = txt.replace("\n", " ")
                txt = fname + ' ' + txt
                if (len(txt.strip().split(',')[1:]) !=0):
                    annotations.append(txt.strip())

        np.random.shuffle(annotations)
        return annotations
    
    def bodylead_lbl_parser(self, x):
        if (x.upper() == "BODY"): 
            return 0
        elif (x.upper() == "PIN" or x.upper() == "PINS"):
             return 1
        else:
            return int(float(x))


    def parse_annotation(self, annotation):

        line = annotation.split()
        image_path = line[0]
        image_path = image_path[:-4] + ".jpg"
        if not os.path.exists(image_path):
            raise KeyError("%s does not exist ... " %image_path)
        image = np.array(cv2.imread(image_path))
        
        # print(line, image_path)
        bboxes = np.array([list(map(self.bodylead_lbl_parser, box.split(','))) for box in line[1:]])
        bboxes[:, [2,3]]=bboxes[:, [0,1]] + bboxes[:, [2,3]]

        # Sanity check
        if ((bboxes.min()<0)  and (bboxes[:, :-1] !=0)):
            raise KeyError ("Error (parse_annotation(self, annotation)): bboxes.min()<0 ")
        if (bboxes[:,[0,2]].max()>image.shape[1] ):
            raise KeyError("Error (parse_annotation(self, annotation)): bboxes[:,[0,2]].max()>image.shape[1] ")
        if (bboxes[:,[1,3]].max()>image.shape[0] ):
            raise KeyError("Error (parse_annotation(self, annotation)): bboxes[:,[1,3]].max()>image.shape[0] ")
        if (len(bboxes[bboxes[:, 4]==0]) > 1):
            raise KeyError("Error (parse_annotation(self, annotation)): len(bboxes[bboxes[:, 4]==0]) > 1")
        if (len(bboxes[bboxes[:, 4]==0]) == 0):
            with  open("./data/log/DatabaseParsing_Error.txt", "a") as myfile:
                print(line, image_path)
                myfile.write(annotation.split()[0])
                myfile.write("\n")
            # raise KeyError("Error (parse_annotation(self, annotation)): len(bboxes[bboxes[:, 4]==0]) != 0 ")

        # Augmentations
        if self.data_aug:
            image, bboxes = self.random_horizontal_flip(np.copy(image), np.copy(bboxes))
            image, bboxes = self.random_crop(np.copy(image), np.copy(bboxes))
            image, bboxes = self.random_translate(np.copy(image), np.copy(bboxes))

        # Preprocessing aka resizing
        image, bboxes = utils.image_preporcess(np.copy(image), [self.train_input_size, self.train_input_size], np.copy(bboxes))
        
        # Sanity check
        if (bboxes.min()<0):
            if (bboxes_xywh[:,[0,2]].max()>image.shape[1]): 
                print("ERROR: Location exceed image width by",bboxes_xywh[:,2].max()-image.shape[1])
            if (bboxes_xywh[:,[1,3]].max()>image.shape[0] ):
                print("ERROR: Location exceed image height by",bboxes_xywh[:,3].max()-image.shape[0])

            with  open("./data/log/DatabaseParsing_Error.txt", "a") as myfile:
                myfile.write(annotation.split()[0])
                myfile.write("\n")
            # raise KeyError("Error: Mismatched dimension! ", bboxes_xywh)
            
        return image, bboxes


class MultichannelDataset(Dataset):

    def __init__(self, dataset_type):
        super().__init__(dataset_type)

    def parse_annotation(self, annotation):
        line = annotation.split()
        image_path = line[0]
        if not os.path.exists(image_path):
            raise KeyError("%s does not exist ... " %image_path)
        image = np.array(cv2.imread(image_path))
        image = np.concatenate((image, image), axis=2)
        # cv2.imwrite("a.png",image[:,:,1])
        
        bboxes = np.array([list(map(lambda x: int(float(x)), box.split(','))) for box in line[1:]])

        for i in range(self.channels):
            name="MultichannelDataset-BF-{}.png".format(i)
            cv2.imwrite(name,image[:,:,i])

        if self.data_aug:
            image, bboxes = self.random_horizontal_flip(np.copy(image), np.copy(bboxes))
            # cv2.imwrite("b.png",image[:,:,1])
            image, bboxes = self.random_crop(np.copy(image), np.copy(bboxes))
            # cv2.imwrite("c.png",image[:,:,3])
            image, bboxes = self.random_translate(np.copy(image), np.copy(bboxes))
            # cv2.imwrite("d.png",image[:,:,4])

        image, bboxes = utils.image_preporcess_multichannel(np.copy(image), [self.train_input_size, self.train_input_size], np.copy(bboxes))
        
        for i in range(self.channels):
            name="MultichannelDataset-AF-{}.png".format(i)
            cv2.imwrite(name,image[:,:,i] *255.)
        return image, bboxes
        

if __name__ == "__main__":
    
    mydataset = Dataset_LD_ZL('train')
    for i, _ in enumerate(mydataset):
        print(i)
    pass        
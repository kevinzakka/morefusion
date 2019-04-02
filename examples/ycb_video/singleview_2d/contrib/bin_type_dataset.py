import pathlib

import imgviz
import numpy as np

import objslampp
import trimesh.transformations as tf


class BinTypeDataset(objslampp.datasets.DatasetBase):

    def __init__(self, root_dir, class_ids=None):
        super().__init__()
        self._root_dir = pathlib.Path(root_dir)
        self._class_ids = class_ids
        self._ids = self._get_ids()

    def _get_ids(self):
        ids = []
        for video_dir in sorted(self.root_dir.iterdir()):
            for npz_file in sorted(video_dir.iterdir()):
                frame_id = f'{npz_file.parent.name}/{npz_file.stem}'
                ids.append(frame_id)
        return ids

    def _get_invalid_data(self):
        return dict(
            class_id=-1,
            rgb=np.zeros((256, 256, 3), dtype=np.uint8),
            quaternion_true=np.zeros((4,), dtype=np.float64),
            translation_true=np.zeros((3,), dtype=np.float64),
            translation_rough=np.zeros((3,), dtype=np.float64),
        )

    def get_frame(self, index):
        frame_id = self.ids[index]
        npz_file = self.root_dir / f'{frame_id}.npz'
        example = np.load(npz_file)
        return dict(
            rgb=example['rgb'],
            intrinsic_matrix=example['intrinsic_matrix'],
        )

    def get_example(self, index):
        frame_id = self.ids[index]
        npz_file = self.root_dir / f'{frame_id}.npz'
        example = np.load(npz_file)

        class_ids = example['class_ids']
        instance_ids = example['instance_ids']
        Ts_cad2cam = example['Ts_cad2cam']

        keep = class_ids > 0
        class_ids = class_ids[keep]
        instance_ids = instance_ids[keep]
        Ts_cad2cam = Ts_cad2cam[keep]

        if self._class_ids is None:
            class_id = np.random.choice(class_ids)
        elif not any(c in class_ids for c in self._class_ids):
            return self._get_invalid_data()
        else:
            class_id = np.random.choice(self._class_ids)

        instance_index = np.where(class_ids == class_id)[0][0]
        instance_id = instance_ids[instance_index]

        mask = example['instance_label'] == instance_id
        bbox = objslampp.geometry.masks_to_bboxes([mask])[0]
        y1, x1, y2, x2 = bbox.round().astype(int)

        if (y2 - y1) * (x2 - x1) == 0:
            return self._get_invalid_data()

        rgb = example['rgb'].copy()
        rgb[~mask] = 0
        rgb = rgb[y1:y2, x1:x2]
        rgb = imgviz.centerize(rgb, (256, 256))

        depth = example['depth']
        K = example['intrinsic_matrix']
        pcd = objslampp.geometry.pointcloud_from_depth(
            depth, fx=K[0, 0], fy=K[1, 1], cx=K[0, 2], cy=K[1, 2],
        )
        translation_rough = np.nanmean(pcd[mask], axis=0)

        T_cad2cam = Ts_cad2cam[instance_index]
        quaternion_true = tf.quaternion_from_matrix(T_cad2cam)
        translation_true = tf.translation_from_matrix(T_cad2cam)

        return dict(
            class_id=class_id,
            rgb=rgb,
            quaternion_true=quaternion_true,
            translation_true=translation_true,
            translation_rough=translation_rough,
        )

import time

import text_detector_craft
from text_detector_craft import file_utils
from text_detector_craft.text_detector_wrapper import TextDetectorWrapper

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
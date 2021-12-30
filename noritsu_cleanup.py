from pathlib import Path

# assume folder structure:
# 20211226/
#   00007466/
#     000074660001_00.jpg
#     000074660002_0.jpg
#     000074660003_1.jpg
#   00007467/
#     ...
#   00007468/
#     ...


class NoritsuEZCCleaner:
    def __init__(self):
        pass

    def find_all_image_dirs(self):
        """
        EZController exports images into a dir for each order number, where the
        directory name is just the order number, zero-padded to 8 characters.
        So we just need to find all directories that are named with 8 digits.
        """
        return Path.cwd().glob("**/" + ("[0-9]" * 8))

    def rename_images(self, images_dir, roll_padding=4, frame_padding=2):
        """
        Renames the images in the images_dir directory in the format:
            R{roll_number}F{frame_name}.jpg (or .tif)

        roll_padding is how many characters of zero padding to add for the
        roll number
        frame_padding is how many characters of zero padding to add for the
        frame name
        """
        pass

    def add_date_info(self, images_dir):
        """
        Adds the DateTimeOriginal EXIF tag to all images, based on the
        filesystem creation timestamp of the file. This fixes the issue where
        rotating a file in Finder or Adobe Bridge will adjust the image's
        modified timestamp, messing up programs that sort by Capture Time
        (such as Lightroom).
        """
        pass

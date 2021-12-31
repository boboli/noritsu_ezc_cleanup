from pathlib import Path

import argparse
import re

# assume folder structure:
# 20211226/  <- date
#   00007466/  <- roll/order number
#     000074660001_00.jpg  <- roll/order number + frame number + frame name
#     000074660002_0.jpg
#     000074660003_1.jpg
#   00007467/
#     ...
#   00007468/
#     ...


class NoritsuEZCCleaner:
    IMAGE_NAME_PATTERN = \
        r"(?P<roll_number>\d{8})" \
        r"(?P<frame_number>\d{4})" \
        r"_" \
        r"(?P<frame_name>.*)"
    image_name_matcher = re.compile(IMAGE_NAME_PATTERN)

    def __init__(self, search_path=None):
        """
        search_path is a str representing the path to search for images to fix.
        If not provided, search_path will be the current working directory.
        """
        if not search_path:
            self.search_path = Path.cwd()
        else:
            self.search_path = Path(search_path)

    def clean(self):
        for image_dir in sorted(self.find_all_image_dirs()):
            self.rename_images(image_dir)

    def find_all_image_dirs(self):
        """
        EZController exports images into a dir for each order number, where the
        directory name is just the order number, zero-padded to 8 characters.
        So we just need to find all directories that are named with 8 digits.

        Unfortunately, the parent directory (which is the date) is also 8
        digits...
        """
        return self.search_path.glob("**/" + ("[0-9]" * 8))

    def rename_images(self, images_dir,
                      roll_padding=4, use_frame_names=False):
        """
        Renames the images in the images_dir directory in the format:
            R{roll_number}F{frame_name}.jpg (or .tif)

        images_dir is a path object that represents the directory of images to
        operate on.
        roll_padding is how many characters of zero padding to add for the
        roll number
        use_frame_names is whether to use the DX reader frame numbers/names
        in the final filename or just number them sequentially.
        """
        roll_number = None
        for image_path in sorted(images_dir.glob("*")):
            filename = image_path.stem  # the filename without extension
            prefix = image_path.parent  # the full path of the parent dir
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() not in (".jpg", ".tif"):
                continue

            match = self.image_name_matcher.match(filename)
            if not match:
                raise ValueError(
                    f"image filename doesn't match expected format: "
                    f"{image_path}")

            if not roll_number:
                roll_number = match.group("roll_number")
            elif roll_number != match.group("roll_number"):
                raise ValueError(
                    f"image filename doesn't match other files: {image_path}")

            # convert roll number to an int, and then zero pad it as desired
            formatted_roll_number = f"{int(roll_number):0>{roll_padding}d}"
            if use_frame_names:
                print("WARNING: this may cause files to be deleted due to "
                      "multiple files having the same frame name such as "
                      "### or for cases of film with no rebate")
                frame_name = match.group("frame_name")
            else:
                frame_number = match.group("frame_number")
                frame_name = f"{int(frame_number):0>2d}"
            new_filename = f"R{formatted_roll_number}F{frame_name}"

            new_filepath = prefix.joinpath(f"{new_filename}{suffix}")
            print(f"{filename} => {new_filename}")
            # image_path.rename(new_filepath)

    def add_date_info(self, images_dir):
        """
        Adds the DateTimeOriginal EXIF tag to all images, based on the
        filesystem creation timestamp of the file. This fixes the issue where
        rotating a file in Finder or Adobe Bridge will adjust the image's
        modified timestamp, messing up programs that sort by Capture Time
        (such as Lightroom).

        images_dir is a path object that represents the directory of images to
        operate on.
        """
        pass


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Sanitizes Noritsu scan files by renaming images and "
        "correcting EXIF metadata."
    )
    parser.add_argument(
        "search_path", nargs="?", default=None,
        help="The path to search for Noritsu scan files. If not provided, "
        "will use current working directory."
    )

    args = parser.parse_args()

    cleaner = NoritsuEZCCleaner(args.search_path)
    cleaner.clean()

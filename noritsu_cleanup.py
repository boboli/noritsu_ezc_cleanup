from pathlib import Path
from datetime import datetime

import argparse
import exif
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
    IMAGE_DIR_GLOB_PATTERN = "[0-9]" * 8
    IMAGE_NAME_PATTERN = \
        r"(?P<roll_number>\d{8})" \
        r"(?P<frame_number>\d{4})" \
        r"_" \
        r"(?P<frame_name>.*)"
    image_name_matcher = re.compile(IMAGE_NAME_PATTERN)

    def __init__(self,
                 search_path=None,
                 roll_padding=4,
                 use_frame_names=False):
        """
        search_path is a str representing the path to search for images to fix.
        If not provided, search_path will be the current working directory.
        roll_padding is how many characters of zero padding to add for the
        roll number
        use_frame_names is whether to use the DX reader frame numbers/names
        in the final filename or just number them sequentially.
        """
        if not search_path:
            self.search_path = Path.cwd()
        else:
            self.search_path = Path(search_path)

        self.roll_padding = roll_padding
        self.use_frame_names = use_frame_names
        if use_frame_names:
            print("WARNING: this may cause files to be deleted due to "
                  "multiple files having the same frame name such as "
                  "### or for cases of film with no rebate")

    def clean(self):
        for image_dir in self.find_all_image_dirs():
            self.fix_timestamps(image_dir)
            self.rename_images(image_dir)

    def find_all_image_dirs(self):
        """
        EZController exports images into a dir for each order number, where the
        directory name is just the order number, zero-padded to 8 characters.
        So we just need to find all directories that are named with 8 digits.

        Unfortunately, the parent directory (which is the date) is also 8
        digits...
        """
        found_dirs = []
        # if the search_path itself is a image dir, add it to beginning of
        # results
        if self.search_path.is_dir() and self.search_path.match(
                self.IMAGE_DIR_GLOB_PATTERN):
            found_dirs.append(self.search_path)
        found_dirs += sorted(
            self.search_path.glob("**/" + self.IMAGE_DIR_GLOB_PATTERN))

        return found_dirs

    def rename_images(self, images_dir):
        """
        Renames the images in the images_dir directory in the format:
            R{roll_number}F{frame_name}.jpg (or .tif)

        images_dir is a path object that represents the directory of images to
        operate on.
        """
        roll_number = None
        for image_path in sorted(images_dir.glob("*")):
            filename = image_path.stem  # the filename without extension
            prefix = image_path.parent  # the full path of the parent dir
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() not in (".jpg", ".tif") or \
                    not image_path.is_file():
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
            formatted_roll_number = \
                f"{int(roll_number):0>{self.roll_padding}d}"
            if self.use_frame_names:
                frame_name = match.group("frame_name")
            else:
                frame_number = match.group("frame_number")
                frame_name = f"{int(frame_number):0>2d}"
            new_filename = f"R{formatted_roll_number}F{frame_name}"

            new_filepath = prefix.joinpath(f"{new_filename}{suffix}")
            print(f"{image_path.name} => {new_filename}{suffix}")
            # image_path.rename(new_filepath)

    def fix_timestamps(self, images_dir):
        """
        Adds the DateTimeOriginal EXIF tag to all images, based on the
        filesystem modified timestamp of the file. This fixes the issue where
        rotating a file in Finder or Adobe Bridge will adjust the image's
        modified timestamp, messing up programs that sort by Capture Time
        (such as Lightroom).

        We set the capture times of the files as such:
            1st image gets the same capture time as its file modified time.
            2nd image gets the 1st image's capture time, but +1 millisecond.
            3rd image gets the 1st image's capture time, but +2 milliseconds.

        We can't just save each image's modified time as its capture time
        because EZController doesn't guarantee that it saves the images in
        sequential order, sometimes a later frame gets saved before an earlier
        one.

        The adding of milliseconds helps preserve the sorting order in programs
        like Lightroom since the ordering is also enforced by the capture time
        set.  If all files got the same capture time, and we were saving the
        frame name in the filenames, we would get cases where ###, 00, 0, E, XA
        frames get out of order, because LR would have to use filename to sort
        since they'd all have the same capture time.

        images_dir is a path object that represents the directory of images to
        operate on.
        """
        first_image_mtime = None
        image_num = 0
        for image_path in sorted(images_dir.glob("*")):
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() not in (".jpg", ".tif") or \
                    not image_path.is_file():
                continue
            # only bump counter for jpgs and tiffs
            image_num += 1

            if not first_image_mtime:
                first_image_mtime = datetime.fromtimestamp(
                    image_path.stat().st_mtime)

            with image_path.open("rb") as image_file:
                exif_image = exif.Image(image_file)

            # image ordering is preserved in the capture time saved,
            # see above docstring
            exif_image.datetime_original = first_image_mtime.strftime(
                exif.DATETIME_STR_FORMAT)
            exif_image.datetime_digitized = first_image_mtime.strftime(
                exif.DATETIME_STR_FORMAT)
            # There's 3 decimal places for the milliseconds, so zero-pad to 3
            exif_image.subsec_time_original = f"{image_num - 1:0>3d}"
            exif_image.subsec_time_digitized = f"{image_num - 1:0>3d}"

            print(f"{image_path.name} getting datetime: "
                  f"{exif_image.datetime_original}:"
                  f"{exif_image.subsec_time_original}")

            # with image_path.open("wb") as image_file_write:
            #     image_file_write.write(exif_image.get_file())


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

    parser.add_argument(
        "--roll_padding", type=int, default=4,
        help="how many characters of zero padding to add for the roll number. "
        "default: 4"
    )
    parser.add_argument(
        "--use_frame_names", type=bool, default=False,
        help="use_frame_names is whether to use the DX reader frame "
        "numbers/names in the final filename or just number them "
        "sequentially. default: False"
    )

    args = parser.parse_args()

    cleaner = NoritsuEZCCleaner(
        search_path=args.search_path,
        roll_padding=args.roll_padding,
        use_frame_names=args.use_frame_names)
    cleaner.clean()

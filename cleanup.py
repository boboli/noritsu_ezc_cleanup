from pathlib import Path
from datetime import datetime

import argparse
import exiftool
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
    EXIF_DATETIME_STR_FORMAT = "%Y:%m:%d %H:%M:%S"
    EXIFTOOL_SUCCESSFUL_WRITE_MESSAGE = "1 image files updated"
    IMAGE_DIR_GLOB_PATTERN = "[0-9]" * 8
    IMAGE_NAME_PATTERN = \
        r"(?P<roll_number>\d{8})" \
        r"(?P<frame_number>\d{4})" \
        r"(_(?P<frame_name>.*))?"
    image_name_matcher = re.compile(IMAGE_NAME_PATTERN)

    def __init__(self,
                 exiftool_client,
                 search_path=None,
                 roll_padding=4,
                 use_frame_names=False):
        """
        exiftool_client is a exiftool.ExifToolHelper object that will be used
        to perform all EXIF modifications required.
        search_path is a str representing the path to search for images to fix.
        If not provided, search_path will be the current working directory.
        roll_padding is how many characters of zero padding to add for the
        roll number
        use_frame_names is whether to use the DX reader frame numbers/names
        in the final filename or just number them sequentially.
        """
        self.exiftool = exiftool_client

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
            try:
                self.delete_thm_files(image_dir)
                self.delete_infohd_file(image_dir)
                self.fix_timestamps(image_dir)
                self.rename_images(image_dir)
            except ValueError as e:
                print(e)
                print(f"skipping directory {image_dir}...")

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
        if self.search_path.is_dir() and \
                re.match(self.IMAGE_DIR_GLOB_PATTERN, self.search_path.name):
            found_dirs.append(self.search_path)
        found_dirs += sorted(
            self.search_path.glob("**/" + self.IMAGE_DIR_GLOB_PATTERN))

        return found_dirs

    def delete_infohd_file(self, images_dir):
        """
        Deletes the Info_HD.txt file that EZC generates if you ask it to always
        save to HDD without confirming.

        images_dir is a path object that represents the directory of images to
        operate on.
        """
        infohd_path = images_dir.joinpath("Info_HD.txt")
        if infohd_path.exists() and infohd_path.is_file():
            print(f"deleting {infohd_path}")
            infohd_path.unlink()

    def delete_thm_files(self, images_dir):
        """
        Deletes the *.thm thumbnail files that EZC generates when outputting
        TIFFs.

        images_dir is a path object that represents the directory of images to
        operate on.
        """
        for thm_file in images_dir.glob("*.thm"):
            if thm_file.exists() and thm_file.is_file():
                print(f"deleting {thm_file}")
                thm_file.unlink()

    def rename_images(self, images_dir):
        """
        Renames the images in the images_dir directory in the format:
            R{roll_number}F{frame_name}.jpg (or .tif)

        images_dir is a path object that represents the directory of images to
        operate on
        """
        roll_number = None
        for image_path in sorted(images_dir.glob("*")):
            filename = image_path.stem  # the filename without extension
            prefix = image_path.parent  # the full path of the parent dir
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() not in (".jpg", ".tif") or \
                    str(filename).startswith(".") or not image_path.is_file():
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
                    f"image has different roll number than other files: "
                    f"{image_path}")

            # convert roll number to an int, and then zero pad it as desired
            formatted_roll_number = \
                f"{int(roll_number):0>{self.roll_padding}d}"
            if self.use_frame_names:
                frame_name = match.group("frame_name")
                if not frame_name:
                    raise ValueError(
                        f"image filename doesn't contain the frame name:"
                        f"{image_path}")
            else:
                frame_number = match.group("frame_number")
                frame_name = f"{int(frame_number):0>2d}"
            new_filename = f"R{formatted_roll_number}F{frame_name}"

            new_filepath = prefix.joinpath(f"{new_filename}{suffix}")
            print(f"{image_path.name} => {new_filename}{suffix}")
            image_path.rename(new_filepath)

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
            filename = image_path.stem  # the filename without extension
            suffix = image_path.suffix  # the extension including the .

            if str(suffix).lower() not in (".jpg", ".tif") or \
                    str(filename).startswith(".") or not image_path.is_file():
                continue

            match = self.image_name_matcher.match(filename)
            if not match:
                raise ValueError(
                    f"image filename doesn't match expected format: "
                    f"{image_path}")

            # only bump counter for jpgs and tiffs
            image_num += 1

            if not first_image_mtime:
                first_image_mtime = datetime.fromtimestamp(
                    image_path.stat().st_mtime)

            # image ordering is preserved in the capture time saved,
            # see above docstring
            datetime_original = first_image_mtime.strftime(
                self.EXIF_DATETIME_STR_FORMAT)
            datetime_digitized = first_image_mtime.strftime(
                self.EXIF_DATETIME_STR_FORMAT)
            # There's 3 decimal places for the milliseconds, so zero-pad to 3
            subsec_time_original = f"{image_num - 1:0>3d}"
            subsec_time_digitized = f"{image_num - 1:0>3d}"

            tags_to_write = {
                "EXIF:DateTimeOriginal": datetime_original,
                "EXIF:DateTimeDigitized": datetime_digitized,
                "EXIF:SubSecTimeOriginal": subsec_time_original,
                "EXIF:SubSecTimeDigitized": subsec_time_digitized,
            }

            print(f"{image_path.name} getting datetime: "
                  f"{datetime_original}:"
                  f"{subsec_time_original}")

            try:
                result = self.exiftool.set_tags(str(image_path), tags_to_write)
            except exiftool.exceptions.ExifToolExecuteError as err:
                print(f"exiftool error while updating timestamps on image: "
                      f"{image_path}")
                print(f"error: {err.stdout}")
            else:
                result = result.strip()
                if result != self.EXIFTOOL_SUCCESSFUL_WRITE_MESSAGE:
                    print(f"failed to update timestamps on image: "
                          f"{image_path}")
                    print(f"exiftool: {result}")


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
        "--use_frame_names", action="store_true",
        help="use_frame_names is whether to use the DX reader frame "
        "numbers/names in the final filename or just number them "
        "sequentially. default: False"
    )

    args = parser.parse_args()

    # the -G and -n are the default common args, -overwrite_original makes sure
    # to not leave behind the "original" files
    common_args = ["-G", "-n", "-overwrite_original"]
    with exiftool.ExifToolHelper(common_args=common_args) as et:
        cleaner = NoritsuEZCCleaner(
            exiftool_client=et,
            search_path=args.search_path,
            roll_padding=args.roll_padding,
            use_frame_names=args.use_frame_names)
        cleaner.clean()

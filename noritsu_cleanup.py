from pathlib import Path
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

    def __init__(self):
        pass

    def clean(self):
        for image_dir in self.find_all_image_dirs():
            self.rename_images(image_dir)

    def find_all_image_dirs(self):
        """
        EZController exports images into a dir for each order number, where the
        directory name is just the order number, zero-padded to 8 characters.
        So we just need to find all directories that are named with 8 digits.

        Unfortunately, the parent directory (which is the date) is also 8
        digits...
        """
        return Path.cwd().glob("**/" + ("[0-9]" * 8))

    def rename_images(self, images_dir, roll_padding=4):
        """
        Renames the images in the images_dir directory in the format:
            R{roll_number}F{frame_name}.jpg (or .tif)

        roll_padding is how many characters of zero padding to add for the
        roll number
        """
        roll_number = None
        for image_path in images_dir.glob("*"):
            filename = image_path.stem
            prefix = image_path.parent
            suffix = image_path.suffix

            if suffix not in (".jpg", ".tif"):
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
            formatted_roll_number = f"{int(roll_number):0>{roll_padding}d}"

            frame_name = match.group("frame_name")
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
        """
        pass


if __name__ == "__main__":
    cleaner = NoritsuEZCCleaner()
    cleaner.clean()

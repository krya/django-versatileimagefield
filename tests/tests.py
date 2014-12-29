import os
from shutil import rmtree

from django.conf import settings
from django.contrib.auth.models import User
from django.core.cache import cache
from django.core.exceptions import ImproperlyConfigured, ValidationError
from django.test import Client, TestCase

from PIL import Image, ImageChops
from versatileimagefield.datastructures.filteredimage import InvalidFilter
from versatileimagefield.datastructures.sizedimage import \
    MalformedSizedImageKey
from versatileimagefield.image_warmer import VersatileImageFieldWarmer
from versatileimagefield.settings import VERSATILEIMAGEFIELD_SIZED_DIRNAME,\
    VERSATILEIMAGEFIELD_FILTERED_DIRNAME
from versatileimagefield.utils import (
    get_rendition_key_set,
    InvalidSizeKey,
    InvalidSizeKeySet
)
from versatileimagefield.validators import validate_ppoi_tuple

from .models import VersatileImageTestModel
from .serializers import VersatileImageTestModelSerializer


class VersatileImageFieldTestCase(TestCase):
    fixtures = ['versatileimagefield']

    def setUp(self):
        self.jpg = VersatileImageTestModel.objects.get(img_type='jpg')
        self.png = VersatileImageTestModel.objects.get(img_type='png')
        self.gif = VersatileImageTestModel.objects.get(img_type='gif')
        password = '12345'
        user = User.objects.create_user(
            username='test',
            email='test@test.com',
            password=password
        )
        user.is_active = True
        user.is_staff = True
        user.is_superuser = True
        user.save()
        client = Client()
        login = client.login(
            username='test',
            password=password
        )
        self.assertTrue(login)
        self.user = user
        self.client = client

    def tearDown(self):
        """
        Deletes files made by VersatileImageFields during tests
        """
        filtered_path = os.path.join(
            settings.MEDIA_ROOT,
            VERSATILEIMAGEFIELD_FILTERED_DIRNAME
        )
        sized_path = os.path.join(
            settings.MEDIA_ROOT,
            VERSATILEIMAGEFIELD_SIZED_DIRNAME
        )
        rmtree(filtered_path, ignore_errors=True)
        rmtree(sized_path, ignore_errors=True)

    @staticmethod
    def imageEqual(image1, image2):
        """
        Returns a bool signifying whether or not `image1` and `image2`
        are identical
        """
        return ImageChops.difference(image1, image2).getbbox() is None

    @staticmethod
    def bad_ppoi():
        """
        Accepts a VersatileImageFieldFile instance and attempts to
        assign a bad PPOI value to it. Should raise a ValidationError
        """
        versatileimagefield = VersatileImageTestModel.objects.get(
            img_type='jpg'
        ).image
        versatileimagefield.ppoi = (1.5, 2)

    @staticmethod
    def bad_ppoi_2():
        """
        Accepts a VersatileImageFieldFile instance and attempts to
        assign a bad PPOI value to it. Should raise a ValidationError
        """
        versatileimagefield = VersatileImageTestModel.objects.get(
            img_type='jpg'
        ).image
        versatileimagefield.ppoi = 'picklexcucumber'

    def test_check_storage_paths(self):
        """Ensure storage paths are properly set"""
        self.assertEqual(self.jpg.image.name, 'python-logo.jpg')
        self.assertEqual(self.png.image.name, 'python-logo.png')
        self.assertEqual(self.gif.image.name, 'python-logo.gif')

    def test_thumbnail_resized_path(self):
        """Ensure thumbnail Sizer paths are set correctly"""
        self.assertEqual(
            self.jpg.image.thumbnail['100x100'].url,
            '/media/__sized__/python-logo-thumbnail-100x100.jpg'
        )

    def test_crop_resized_path(self):
        """Ensure crop Sizer paths are set correctly"""
        self.assertEqual(
            self.jpg.image.crop['100x100'].url,
            '/media/__sized__/python-logo-crop-c0-25__0-25-100x100.jpg'
        )
        self.assertEqual(
            self.gif.image.crop['100x100'].url,
            '/media/__sized__/python-logo-crop-c0-75__0-75-100x100.gif'
        )
        self.assertEqual(
            self.png.image.crop['100x100'].url,
            '/media/__sized__/python-logo-crop-c0-5__0-5-100x100.png'
        )

    def test_invert_filtered_path(self):
        """Ensure crop Sizer paths are set correctly"""
        self.assertEqual(
            self.jpg.image.filters.invert.url,
            '/media/__filtered__/python-logo__invert__.jpg'
        )

    def invalid_filter_access(self):
        """
        Attempts to access a non-existant filter.
        Should raise InvalidFilter
        """
        invalid_filter = self.jpg.image.filters.non_existant.url
        del invalid_filter

    def test_InvalidFilter(self):
        """Ensure InvalidFilter raises"""
        self.assertRaises(
            InvalidFilter,
            self.invalid_filter_access
        )

    def test_invert_plus_thumbnail_sizer_filtered_path(self):
        """Ensure crop Sizer paths are set correctly"""
        self.assertEqual(
            self.jpg.image.filters.invert.thumbnail['100x100'].url,
            (
                '/media/__sized__/__filtered__/python-logo__invert__'
                '-thumbnail-100x100.jpg'
            )
        )

    def test_placeholder_image(self):
        """Ensures placehold.it integration"""
        self.assertEqual(
            self.jpg.optional_image.crop['100x100'].url,
            'http://placehold.it/100x100'
        )

    def test_setting_ppoi_values(self):
        """Ensure PPOI values are set correctly"""
        jpg = VersatileImageTestModel.objects.get(img_type='jpg')
        self.assertEqual(
            jpg.image.ppoi,
            (0.25, 0.25)
        )
        jpg.image.ppoi = (0.5, 0.5)
        jpg.save()
        self.assertEqual(
            jpg.image.ppoi,
            (0.5, 0.5)
        )
        jpg.image.ppoi = '0.25x0.25'
        jpg.save()
        self.assertEqual(
            jpg.image.ppoi,
            (0.25, 0.25)
        )
        self.assertRaises(ValidationError, self.bad_ppoi)
        self.assertRaises(ValidationError, self.bad_ppoi_2)

    def test_invalid_ppoi_tuple_validation(self):
        """
        Ensure validate_ppoi_tuple works as expected
        """
        self.assertFalse(
            validate_ppoi_tuple((0, 1.5, 6))
        )

    @staticmethod
    def try_invalid_create_on_demand_set():
        """
        Attempts to assign a non-bool value to a VersatileImageField's
        `create_on_demand` attribute
        Should raise ValueError
        """
        jpg = VersatileImageTestModel.objects.get(img_type='jpg')
        jpg.image.create_on_demand = 'pickle'

    def test_create_on_demand_boolean(self):
        """Ensure create_on_demand boolean is set appropriately"""
        jpg = VersatileImageTestModel.objects.get(img_type='jpg')
        self.assertFalse(jpg.image.create_on_demand)
        jpg.image.create_on_demand = True
        self.assertTrue(jpg.image.create_on_demand)
        self.assertRaises(
            ValueError,
            self.try_invalid_create_on_demand_set
        )

    def test_create_on_demand_functionality(self):
        """Ensures create_on_demand functionality works as advertised"""
        jpg = VersatileImageTestModel.objects.get(img_type='jpg')
        img_url = jpg.image.crop['100x100'].url
        self.assertEqual(
            cache.get(img_url),
            None
        )
        jpg.image.create_on_demand = True
        jpg.image.crop['100x100'].url
        self.assertEqual(
            cache.get(img_url),
            1
        )
        self.assertTrue(
            jpg.image.field.storage.exists(jpg.image.crop['100x100'].name)
        )
        jpg.image.field.storage.delete(jpg.image.crop['100x100'].name)
        self.assertFalse(
            jpg.image.field.storage.exists(jpg.image.crop['100x100'].name)
        )
        cache.delete(img_url)
        self.assertEqual(
            cache.get(img_url),
            None
        )

    @staticmethod
    def invalid_image_warmer():
        """
        Instantiates a VersatileImageFieldWarmer with something other than
        a model instance or queryset.
        Should raise ValueError
        """
        invalid_warmer = VersatileImageFieldWarmer(
            instance_or_queryset=['invalid'],
            rendition_key_set=(
                ('test_thumb', 'thumbnail__100x100'),
            ),
            image_attr='image'
        )
        del invalid_warmer

    def test_image_warmer(self):
        """Ensures VersatileImageFieldWarmer works as advertised."""
        jpg_warmer = VersatileImageFieldWarmer(
            instance_or_queryset=self.jpg,
            rendition_key_set='test_set',
            image_attr='image'
        )
        num_created, failed_to_create = jpg_warmer.warm()
        self.assertEqual(num_created, 5)
        all_imgs_warmer = VersatileImageFieldWarmer(
            instance_or_queryset=VersatileImageTestModel.objects.all(),
            rendition_key_set=(
                ('test_thumb', 'thumbnail__100x100'),
                ('test_invert', 'filters__invert__url'),
            ),
            image_attr='image',
            verbose=True
        )
        num_created, failed_to_create = all_imgs_warmer.warm()
        self.assertRaises(
            ValueError,
            self.invalid_image_warmer
        )

    def test_VersatileImageFieldSerializer_output(self):
        """Ensures VersatileImageFieldSerializer serializes correctly"""
        serializer = VersatileImageTestModelSerializer(self.jpg)
        self.assertEqual(
            serializer.data.get('image'),
            {
                'test_crop': (
                    '/media/__sized__/python-logo-crop-c0-25__'
                    '0-25-100x100.jpg'
                ),
                'test_invert_crop': (
                    '/media/__sized__/__filtered__/python-logo__'
                    'invert__-crop-c0-25__0-25-100x100.jpg'
                ),
                'test_invert_thumb': (
                    '/media/__sized__/__filtered__/python-logo__'
                    'invert__-thumbnail-100x100.jpg'
                ),
                'test_invert': (
                    '/media/__filtered__/python-logo__invert__.jpg'
                ),
                'test_thumb': (
                    '/media/__sized__/python-logo-thumbnail'
                    '-100x100.jpg'
                )
            }
        )

    def test_widget_javascript(self):
        """
        Ensures the VersatileImagePPOIClickWidget widget loads appropriately
        and its image preview is available
        """
        response = self.client.get('/admin/tests/versatileimagetestmodel/1/')
        self.assertEqual(response.status_code, 200)
        self.assertTrue(
            (
                '<img src="/media/__sized__/python-logo-thumbnail-300x300.png"'
                ' id="image_0_imagepreview" data-hidden_field_id="id_image_1"'
                ' data-point_stage_id="image_0_point-stage" '
                'data-ppoi_id="image_0_ppoi" class="sizedimage-preview"/>'
                in response.content
            )
        )
        self.assertTrue(
            (
                '<script type="text/javascript" src="/static/'
                'versatileimagefield/js/versatileimagefield.js"></script>'
                in response.content
            )
        )
        self.assertTrue(
            self.png.image.field.storage.exists(
                self.png.image.thumbnail['300x300'].name
            )
        )

    def test_VersatileImageFieldDescriptor__set__(self):
        """
        Ensures VersatileImageFieldDescriptor.__set__ works as intended
        """
        self.jpg.image = 'python-logo-2.jpg'
        self.jpg.save()
        self.assertEqual(
            self.jpg.image.thumbnail['100x100'].url,
            '/media/__sized__/python-logo-2-thumbnail-100x100.jpg'
        )
        self.jpg.image = 'python-logo.jpg'
        self.jpg.save()
        self.assertEqual(
            self.jpg.image.thumbnail['100x100'].url,
            '/media/__sized__/python-logo-thumbnail-100x100.jpg'
        )

    @staticmethod
    def non_existent_rendition_key_set():
        """
        Tries to retrieve a non-existent rendition key set.
        Should raise ImproperlyConfigured
        """
        get_rendition_key_set('does_not_exist')

    @staticmethod
    def invalid_size_key():
        """
        Tries to validate a Size Key set with an invalid size key.
        Should raise InvalidSizeKey
        """
        get_rendition_key_set('invalid_size_key')

    @staticmethod
    def invalid_size_key_set():
        """
        Tries to retrieve a non-existent rendition key set.
        Should raise InvalidSizeKeySet
        """
        get_rendition_key_set('invalid_set')

    def test_VERSATILEIMAGEFIELD_RENDITION_KEY_SETS_setting(self):
        """
        Ensures VERSATILEIMAGEFIELD_RENDITION_KEY_SETS setting
        validates correctly
        """
        self.assertRaises(
            ImproperlyConfigured,
            self.non_existent_rendition_key_set
        )
        self.assertRaises(
            InvalidSizeKeySet,
            self.invalid_size_key_set
        )
        self.assertRaises(
            InvalidSizeKey,
            self.invalid_size_key
        )

    def test_exif_orientation_rotate_180(self):
        """
        Ensures VersatileImageFields process exif orientation==3 data properly
        """
        exif_3 = VersatileImageTestModel.objects.get(
            img_type='exif_3'
        )
        exif_3.image.create_on_demand = True
        exif_3_img = exif_3.image.field.storage.open(
            exif_3.image.thumbnail['100x100'].name
        )
        exif_3_control = exif_3.image.field.storage.open(
            'verify-against/exif-orientation-examples/'
            'Landscape_3-thumbnail-100x100.jpg'
        )
        self.assertTrue(
            self.imageEqual(
                Image.open(exif_3_img),
                Image.open(exif_3_control)
            )
        )

    def test_exif_orientation_rotate_270(self):
        """
        Ensures VersatileImageFields process exif orientation==6 data properly
        """
        exif_6 = VersatileImageTestModel.objects.get(
            img_type='exif_6'
        )
        exif_6.image.create_on_demand = True
        exif_6_img = exif_6.image.field.storage.open(
            exif_6.image.thumbnail['100x100'].name
        )
        exif_6_control = exif_6.image.field.storage.open(
            'verify-against/exif-orientation-examples/'
            'Landscape_6-thumbnail-100x100.jpg'
        )
        self.assertTrue(
            self.imageEqual(
                Image.open(exif_6_img),
                Image.open(exif_6_control)
            )
        )

    def test_exif_orientation_rotate_90(self):
        """
        Ensures VersatileImageFields process exif orientation==8 data properly
        """
        exif_8 = VersatileImageTestModel.objects.get(
            img_type='exif_8'
        )
        exif_8.image.create_on_demand = True
        exif_8_img = exif_8.image.field.storage.open(
            exif_8.image.thumbnail['100x100'].name
        )
        exif_8_control = exif_8.image.field.storage.open(
            'verify-against/exif-orientation-examples/'
            'Landscape_8-thumbnail-100x100.jpg'
        )
        self.assertTrue(
            self.imageEqual(
                Image.open(exif_8_img),
                Image.open(exif_8_control)
            )
        )

    def test_horizontal_and_vertical_crop(self):
        """
        Tests horizontal and vertical crops with 'extreme' PPOI values
        """
        test_gif = VersatileImageTestModel.objects.get(
            img_type='gif'
        )
        test_gif.image.create_on_demand = True
        test_gif.image.ppoi = (0, 0)
        # Vertical w/ PPOI == '0x0'
        vertical_image_crop = test_gif.image.field.storage.open(
            test_gif.image.crop['10x100'].name
        )
        vertical_image_crop_control = test_gif.image.field.storage.open(
            'verify-against/python-logo-crop-c0__0-10x100.gif'
        )
        self.assertTrue(
            self.imageEqual(
                Image.open(vertical_image_crop),
                Image.open(vertical_image_crop_control)
            )
        )
        # Horizontal w/ PPOI == '0x0'
        horiz_image_crop = test_gif.image.field.storage.open(
            test_gif.image.crop['100x10'].name
        )
        horiz_image_crop_control = test_gif.image.field.storage.open(
            'verify-against/python-logo-crop-c0__0-100x10.gif'
        )
        self.assertTrue(
            self.imageEqual(
                Image.open(horiz_image_crop),
                Image.open(horiz_image_crop_control)
            )
        )

        test_gif.image.ppoi = (1, 1)

        # Vertical w/ PPOI == '1x1'
        vertical_image_crop = test_gif.image.field.storage.open(
            test_gif.image.crop['10x100'].name
        )
        vertical_image_crop_control = test_gif.image.field.storage.open(
            'verify-against/python-logo-crop-c1__1-10x100.gif'
        )
        self.assertTrue(
            self.imageEqual(
                Image.open(vertical_image_crop),
                Image.open(vertical_image_crop_control)
            )
        )
        # Horizontal w/ PPOI == '1x1'
        horiz_image_crop = test_gif.image.field.storage.open(
            test_gif.image.crop['100x10'].name
        )
        horiz_image_crop_control = test_gif.image.field.storage.open(
            'verify-against/python-logo-crop-c1__1-100x10.gif'
        )
        self.assertTrue(
            self.imageEqual(
                Image.open(horiz_image_crop),
                Image.open(horiz_image_crop_control)
            )
        )

    def test_DummyFilter(self):
        """Tests placeholder image functionality for filters"""
        test_jpg = VersatileImageTestModel.objects.get(
            img_type='png'
        )
        test_jpg.optional_image.create_on_demand = True
        test_jpg.optional_image.filters.invert.url

    @staticmethod
    def assign_crop_key():
        """
        Attempts to assign a value to the 'crop' SizedImage subclass

        Should raise NotImplementedError
        """
        jpg = VersatileImageTestModel.objects.get(img_type='jpg')
        jpg.image.crop['100x100'] = None

    @staticmethod
    def assign_thumbnail_key():
        """
        Attempts to assign a value to the 'thumbnail' SizedImage subclass

        Should raise NotImplementedError
        """
        jpg = VersatileImageTestModel.objects.get(img_type='jpg')
        jpg.image.thumbnail['100x100'] = None

    def test_crop_and_thumbnail_key_assignment(self):
        """Tests placeholder image functionality for filters"""
        self.assertRaises(
            NotImplementedError,
            self.assign_crop_key
        )
        self.assertRaises(
            NotImplementedError,
            self.assign_thumbnail_key
        )

    def get_bad_sized_image_key(self):
        """Attempts to retrieve a thumbnail image with a malformed size key"""
        self.jpg.image.thumbnail['fooxbar']

    def test_MalformedSizedImageKey(self):
        """
        Testing MalformedSizedImageKey exception
        """
        self.assertRaises(
            MalformedSizedImageKey,
            self.get_bad_sized_image_key
        )

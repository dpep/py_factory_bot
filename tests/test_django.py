import unittest

import pytest
from support.django_setup import setup

setup()

from django.test import TestCase
from support.django_app.models import Author, Book

from factory_bot import association, create, create_list, f, factory


def define_factories():
    @factory(Author)
    def author():
        f.name = "Ann"

    @factory(Book)
    def book():
        f.title = "Dune"
        f.author = association("author")


class CreateTests(TestCase):
    def setUp(self):
        define_factories()

    def test_create_saves_with_nothing_configured(self):
        book = create("book")
        assert Book.objects.get(pk=book.pk).title == "Dune"

    def test_associations_are_saved_before_the_rows_that_reference_them(self):
        book = create("book")
        assert Book.objects.get(pk=book.pk).author == Author.objects.get()

    def test_django_refuses_a_row_whose_association_is_unsaved(self):
        with pytest.raises(ValueError, match="unsaved related object"):
            Book(title="Orphan", author=Author(name="Bea")).save()

    def test_create_list_saves_each(self):
        create_list("book", 3)
        assert Book.objects.count() == Author.objects.count() == 3


def test_a_django_test_case_rolls_its_rows_back():
    class Case(TestCase):
        def test_create(self):
            create("book")
            assert Book.objects.count() == 1

    define_factories()
    result = unittest.TestResult()
    unittest.defaultTestLoader.loadTestsFromTestCase(Case).run(result)

    assert result.wasSuccessful(), result.errors + result.failures
    assert Book.objects.count() == Author.objects.count() == 0

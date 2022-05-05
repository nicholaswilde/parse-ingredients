import unittest
from parse_ingredients.ingredient import Ingredient 

class TestParseIngredients(unittest.TestCase):
    """"""
    original_string="12 ounces lean ground beef, preferably 85 percent lean"
    ing=Ingredient()
    ing.parse(original_string)

    def test_name(self):
        self.assertEqual("beef",self.ing.name)

    def test_unit(self):
        self.assertEqual("ounce", self.ing.unit)

    def test_quantity(self):
        self.assertEqual("12", self.ing.quantity)

    def test_comment(self):
        self.assertEqual("lean ground, preferably 85 percent lean", self.ing.comment)

    def test_original_string(self):
        self.assertEqual(self.original_string, self.ing.original_string)

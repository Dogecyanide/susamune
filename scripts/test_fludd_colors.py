"""Exercise all ten production FLUDD/water colour editor targets."""
import unittest
import test_mario_colors

class FluddColorTests(test_mario_colors.MarioColorTests):
    GROUP = "Fludd"
    COUNT = 10

if __name__ == "__main__":
    unittest.main()

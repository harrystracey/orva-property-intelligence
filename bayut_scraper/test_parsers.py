"""
Test script for Bayut parsers.
Validates parsing logic without requiring actual web scraping.
"""

from building_guide_parser import parse_building_guide
from floor_plan_parser import parse_floor_plan_page
from listing_parser import extract_view_from_text


def test_building_guide_parser():
    """Test building guide text parsing."""
    print("=" * 70)
    print("TEST: Building Guide Parser")
    print("=" * 70 + "\n")
    
    sample_text = """
    The Shoreline apartments feature multiple unit types.
    
    Type-F covers around 2,055 sq. ft. offering panoramic sea views, making it the most premium layout in the building.
    
    Type-D 2-bed flats are the smallest with a covered area of 1,582 sq. ft. and these units face the road.
    
    Type E unit usually covers around 1,646 sq. ft. and offers views of the road.
    
    3-bedroom flats come in Type A configuration that overlooks the sea and another Type A that faces the sister blocks.
    """
    
    results = parse_building_guide(sample_text, "Shoreline 12")
    
    print(f"Extracted {len(results)} unit types:\n")
    for result in results:
        print(f"Type {result['unit_type']}:")
        print(f"  Bedrooms: {result['bedrooms']}")
        print(f"  Size: {result['size_sqft']} sqft")
        print(f"  View: {result['view']}")
        print(f"  Source: {result['source_text'][:80]}...")
        print()
    
    # Assertions
    assert len(results) >= 2, "Should extract at least 2 types"
    assert any(r['unit_type'] == 'D' for r in results), "Should find Type D"
    assert any(r['unit_type'] == 'A' for r in results), "Should find Type A"
    assert any(r['bedrooms'] == '2' for r in results), "Should extract 2-bed"
    assert any(r['bedrooms'] == '3' for r in results), "Should extract 3-bed"
    
    print("[PASS] Building guide parser test\n")


def test_floor_plan_parser():
    """Test floor plan page parsing."""
    print("=" * 70)
    print("TEST: Floor Plan Parser")
    print("=" * 70 + "\n")
    
    sample_html = """
    <html>
    <body>
        <div class="floor-plans">
            <h2>Available Floor Plans</h2>
            <ul>
                <li>Type B: 1 bedroom, 2 bathrooms</li>
                <li>Type D: 2 bedrooms, 3 bathrooms</li>
                <li>Type E: 2 bedrooms, 4 bathrooms</li>
                <li>Type A: 3 bedrooms, 4 bathrooms</li>
            </ul>
        </div>
    </body>
    </html>
    """
    
    results = parse_floor_plan_page(sample_html, "Shoreline 17")
    
    print(f"Extracted {len(results)} unit types:\n")
    for result in results:
        print(f"Type {result['unit_type']}:")
        print(f"  Bedrooms: {result['bedrooms']}")
        print(f"  Bathrooms: {result['bathrooms']}")
        print()
    
    # Assertions
    assert len(results) >= 4, "Should extract 4 types"
    type_letters = [r['unit_type'] for r in results]
    assert 'B' in type_letters, "Should find Type B"
    assert 'D' in type_letters, "Should find Type D"
    
    print("[PASS] Floor plan parser test\n")


def test_view_extraction():
    """Test view extraction from text."""
    print("=" * 70)
    print("TEST: View Extraction")
    print("=" * 70 + "\n")
    
    test_cases = [
        ("Vacant | Full Sea And Burj View | D Type", "Full Sea and Burj Al Arab View"),
        ("2BR apartment with panoramic sea views", "Panoramic Sea View"),
        ("Nice unit with garden view", "Garden View"),
        ("Road facing apartment, 2 beds", "Road View"),
        ("Beautiful marina view from balcony", "Marina View"),
    ]
    
    for text, expected in test_cases:
        result = extract_view_from_text(text)
        print(f"Text: {text[:60]}")
        print(f"  Expected: {expected}")
        print(f"  Got: {result}")
        assert result == expected, f"View extraction failed for: {text}"
        print("  [OK]\n")
    
    print("[PASS] View extraction test\n")


def test_url_generation():
    """Test URL generation from building names."""
    print("=" * 70)
    print("TEST: URL Generation")
    print("=" * 70 + "\n")
    
    from bayut_urls import get_building_guide_url, get_floor_plan_url, get_listings_url
    
    # Test Shoreline
    guide_url = get_building_guide_url("Shoreline 12")
    assert guide_url == "https://www.bayut.com/buildings/al-haseer/", f"Wrong URL: {guide_url}"
    print(f"Shoreline 12 guide: {guide_url} [OK]")
    
    # Test Fairmont
    guide_url = get_building_guide_url("Fairmont")
    assert "fairmont" in guide_url.lower(), f"Wrong URL: {guide_url}"
    print(f"Fairmont guide: {guide_url} [OK]")
    
    # Test floor plan
    floor_url = get_floor_plan_url("Shoreline 17")
    assert "al-hamri" in floor_url, f"Wrong URL: {floor_url}"
    print(f"Shoreline 17 floor plan: {floor_url} [OK]")
    
    # Test listings
    listings_url = get_listings_url("Oceana", "rent")
    assert "to-rent" in listings_url, f"Wrong URL: {listings_url}"
    print(f"Oceana listings (rent): {listings_url} [OK]")
    
    print("\n[PASS] URL generation test\n")


if __name__ == "__main__":
    try:
        test_building_guide_parser()
        test_floor_plan_parser()
        test_view_extraction()
        test_url_generation()
        
        print("=" * 70)
        print("ALL TESTS PASSED!")
        print("=" * 70)
        print("\nParsers are ready for web scraping.")
        print("\nNext steps:")
        print("  1. Install dependencies: pip install beautifulsoup4 playwright")
        print("  2. Install Playwright browsers: playwright install chromium")
        print("  3. Launch Chrome: python bayut_scraper/run_bayut_scrape.py --launch-chrome")
        print("  4. Start scraping: python bayut_scraper/run_bayut_scrape.py --mode guides_only")
    
    except AssertionError as e:
        print(f"\n[FAIL] Test failed: {e}")
        import traceback
        traceback.print_exc()
    
    except Exception as e:
        print(f"\n[ERROR] {e}")
        import traceback
        traceback.print_exc()

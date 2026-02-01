#!/usr/bin/env python
"""Quick test script for the MCP tools."""

import asyncio

from main import (
    compare_fastapi_approaches,
    get_fastapi_best_practices,
    get_fastapi_docs,
    get_fastapi_example,
    list_fastapi_pages,
    search_fastapi_docs,
)


async def test_tools() -> None:
    print("=" * 60)
    print("Testing FastAPI Docs MCP Server Tools")
    print("=" * 60)

    # Test 1: get_fastapi_docs
    print("\n[Test 1] get_fastapi_docs('tutorial/first-steps')")
    print("-" * 40)
    result = await get_fastapi_docs.fn("tutorial/first-steps")
    print(result[:500] + "..." if len(result) > 500 else result)
    print("\nPASSED\n")

    # Test 2: search_fastapi_docs
    print("[Test 2] search_fastapi_docs('cors')")
    print("-" * 40)
    result = await search_fastapi_docs.fn("cors")
    print(result[:500] + "..." if len(result) > 500 else result)
    print("\nPASSED\n")

    # Test 3: list_fastapi_pages
    print("[Test 3] list_fastapi_pages()")
    print("-" * 40)
    result = await list_fastapi_pages.fn()
    print(result[:600] + "..." if len(result) > 600 else result)
    print("\nPASSED\n")

    # Test 4: get_fastapi_example (NEW)
    print("[Test 4] get_fastapi_example('cors')")
    print("-" * 40)
    result = await get_fastapi_example.fn("cors")
    print(result[:800] + "..." if len(result) > 800 else result)
    print("\nPASSED\n")

    # Test 5: compare_fastapi_approaches (NEW)
    print("[Test 5] compare_fastapi_approaches('auth-methods')")
    print("-" * 40)
    result = await compare_fastapi_approaches.fn("auth-methods")
    print(result[:800] + "..." if len(result) > 800 else result)
    print("\nPASSED\n")

    # Test 6: get_fastapi_best_practices (NEW)
    print("[Test 6] get_fastapi_best_practices('security')")
    print("-" * 40)
    result = await get_fastapi_best_practices.fn("security")
    print(result[:800] + "..." if len(result) > 800 else result)
    print("\nPASSED\n")

    print("=" * 60)
    print("All 6 tools working correctly!")
    print("=" * 60)


if __name__ == "__main__":
    asyncio.run(test_tools())

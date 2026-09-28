#!/usr/bin/env python3
"""omp integration demo - show savings on every turn"""
import sys
sys.path.insert(0, 'src')

from kompressor.engine import KompressorEngine
from kompressor.harnesses.omp import OMPHarnessAdapter
from pathlib import Path

def main():
    # Read actual fixture for realistic test
    text = Path('tests/fixtures/logs.json').read_text()
    
    # Step 1: Optimize with kompressor engine
    engine = KompressorEngine()
    result = engine.optimize(text)
    
    # Step 2: Package for omp harness (includes savings line in content)
    adapter = OMPHarnessAdapter()
    bundle = adapter.package(result, task='Find auth failures')
    
    # Step 3: Show savings (this is what omp should print on each turn)
    print('🎯 OMP Agent Turn Output:')
    print('─' * 60)
    
    # Extract and print the savings line
    for line in bundle.content.split('\n'):
        if 'KOMPRESSOR_TOKEN_SAVINGS' in line:
            print(f'📊 {line}')
            break

if __name__ == '__main__':
    main()
#!/usr/bin/env node
import esbuild from 'esbuild';
import { copyFileSync, mkdirSync } from 'fs';
import { join } from 'path';

const isProduction = process.env.NODE_ENV === 'production';

const options = {
  entryPoints: ['src/js/main.ts'],
  bundle: true,
  minify: isProduction,
  sourcemap: !isProduction,
  format: 'iife',
  target: ['es2020'],
  outfile: 'static/dist/app.js',
  legalComments: 'none',
  logLevel: 'info',
  define: {
    'process.env.NODE_ENV': `"${isProduction ? 'production' : 'development'}"`,
  },
};

async function build() {
  try {
    console.log(`🔨 Building THREAT-AI UI (${isProduction ? 'production' : 'development'})...`);
    
    // Ensure dist directory exists
    mkdirSync('static/dist', { recursive: true });
    
    // Build JavaScript
    await esbuild.build(options);
    
    console.log('✅ Build complete!');
    console.log(`📦 Output: ${options.outfile}`);
    
  } catch (error) {
    console.error('❌ Build failed:', error);
    process.exit(1);
  }
}

build();

/**
 * Vitest runs component tests in Node with renderToStaticMarkup.
 * Ensure classic JSX (React.createElement) has React in scope when transforms fall back.
 */
import * as React from 'react';

(globalThis as typeof globalThis & { React: typeof React }).React = React;

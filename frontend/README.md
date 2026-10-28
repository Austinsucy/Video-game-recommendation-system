# React + TypeScript + Vite

## React Compiler

The React Compiler is not enabled on this template because of its impact on dev & build performances. To add it, see [this documentation](https://react.dev/learn/react-compiler/installation).


# READ (SCRUM 1 October - November)
The current landing page for the website is a shell. 
There is a header where you're able to see the title and a brief description. 
There is a toolbar underneath where there is a search bar, a genre filter, and a scan button that will provide random games until the user decides to stop. 
In the center, an empty space is left for the game map which will eventually be filled with the game nodes. 
On the bottom there is a 'game info' panel where the game's information will be displayed after selection

## CHANGES AS OF 10/27
- Created frontend branch
- Used following commands to ensure consistency for typescript:
'--save-dev' to record typescript as a development tool
'--save-exact' to record specific typescript version: 6.0.3
- used "frontend" template from React and Vite to get a starter landing page
- edited 'App.tsx':
created class name "app shell" and added a header, description, toolbar, map space, and game information panel. All areas are disabled as I have to try and figure out how to call the database aspects to retrieve the game details. 
- created 'shell.css' and removed the starter "App.css"
used shell.css to get the class names in order for App.tsx

## HOW TO START THE FRONT END SHELL


## Expanding the ESLint configuration

If you are developing a production application, we recommend updating the configuration to enable type-aware lint rules:

```js
export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...

      // Remove tseslint.configs.recommended and replace with this
      tseslint.configs.recommendedTypeChecked,
      // Alternatively, use this for stricter rules
      tseslint.configs.strictTypeChecked,
      // Optionally, add this for stylistic rules
      tseslint.configs.stylisticTypeChecked,

      // Other configs...
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

You can also install [eslint-plugin-react-x](https://npmx.dev/package/eslint-plugin-react-x) and [eslint-plugin-react-dom](https://npmx.dev/package/eslint-plugin-react-dom) for React-specific lint rules:

```js
// eslint.config.js
import reactX from 'eslint-plugin-react-x'
import reactDom from 'eslint-plugin-react-dom'

export default defineConfig([
  globalIgnores(['dist']),
  {
    files: ['**/*.{ts,tsx}'],
    extends: [
      // Other configs...
      // Enable lint rules for React
      reactX.configs['recommended-typescript'],
      // Enable lint rules for React DOM
      reactDom.configs.recommended,
    ],
    languageOptions: {
      parserOptions: {
        project: ['./tsconfig.node.json', './tsconfig.app.json'],
        tsconfigRootDir: import.meta.dirname,
      },
      // other options...
    },
  },
])

```

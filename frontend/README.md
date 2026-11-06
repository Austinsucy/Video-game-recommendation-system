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
- You will need NPM in your terminal/commandline
- change your directory to ../video-game-recommendation-system/frontend
- run "npm run build" and then "npm run dev", then enter 'o' and press return/enter

## LAYOUT AND WHERE TO ADD FEATURES (11/2)
The map fills the page under a slim toolbar. Feature buttons sit on the left, search and Help on the right.
Clicking a game opens the information panel on the right; feature panels open on the left.

| File | What it does |
|---|---|
| `src/App.tsx` | Holds the map data, the selected game and the open feature panel. `selectGame` / `selectAndLocate` are the one selection path for clicks, search and (later) scan and similar games. |
| `src/components/map/GameMap.tsx` | Cytoscape map with the stored x/y (preset layout). Exposes `zoomIn`, `zoomOut`, `resetView`, `focusGame(id)` and `focus` through a ref. |
| `src/components/map/mapStyle.ts`, `labelPlacement.ts` | Node and label styling, and which titles get a label (most popular first, no overlaps). |
| `src/components/toolbar/` | Toolbar and search box. Search currently matches titles already loaded from `map.db`. |
| `src/components/info/GameInfoPanel.tsx` | GIP 1 panel. Fields with no data yet say "Unavailable". |
| `src/features/` | One panel per toolbar feature (UDR 1, GV 1, CL 1, SC 1, MCS 1, SI 1, GW 1). Add a button in `features.ts` and a case in `FeaturePanelHost.tsx`. |
| `src/services/gameService.ts` | Reads `map.db`. `getGameDetails` is where `GET /games/{id}` plugs in. |

To build a feature, replace the disabled controls in its panel and mark it `status="partial"` or remove the `PlannedControls` wrapper.

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

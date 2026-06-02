# ORF ATC Sim Deploy

This setup uses GitHub Pages for the static simulator and Render for the small API that talks to OpenAI.

## 1. Publish The Frontend On GitHub Pages

1. Create a GitHub repository.
2. Push this project to the repository.
3. In GitHub, open `Settings > Pages`.
4. Set source to `Deploy from a branch`.
5. Select `main` and `/root`.
6. Save and wait for the Pages URL.

The simulator can run as a static site. The OpenAI voice features need the Render backend below.

## 2. Publish The Backend On Render

1. Create a new Render Web Service from the same GitHub repository.
2. Render should detect `render.yaml`. If setting manually:
   - Root directory: `backend`
   - Build command: `npm install`
   - Start command: `npm start`
3. Add environment variables:
   - `OPENAI_API_KEY`: your OpenAI API key
   - `FRONTEND_ORIGIN`: your GitHub Pages URL, for example `https://yourname.github.io/your-repo`
   - `OPENAI_TRANSCRIBE_MODEL`: `gpt-4o-mini-transcribe`
   - `OPENAI_TTS_MODEL`: `gpt-4o-mini-tts`
4. Deploy the service.
5. Open `https://your-render-service.onrender.com/health` and confirm it returns JSON.

Render free services can sleep after inactivity. The first voice request after sleep may take a moment.

## 3. Connect The Sim To Render

1. Open the GitHub Pages simulator.
2. In the Instructor panel, paste the Render URL into `Backend API URL`.
3. Click `Use`.
4. Use push-to-talk or pilot voice as normal.

Do not put an OpenAI API key in GitHub. For hosted deployment, keep the key only in Render environment variables.

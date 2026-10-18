# Dataset setup

The original dataset is distributed separately because it exceeds GitHub’s regular file-size limit.

To run the notebook or retrain the models:

1. Obtain the original `power_consumption_germany.csv` dataset used by GridAI.
2. Place it in this folder without changing its filename:

   ```text
   GridAI/
   └── data/
       ├── README.md
       └── power_consumption_germany.csv
   ```

3. Open `notebooks.ipynb` from the project folder and run the cells in order.
4. Enable the notebook’s retraining flags only if you want to retrain the supplied models.

The dashboard does not require this raw CSV. It uses the saved models in `backend/models/` and the packaged history and metadata in `backend/data/`.

Keep those backend folders and their required files intact.

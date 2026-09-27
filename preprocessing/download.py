import os
import wfdb
import logging

logging.basicConfig(level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)

def download_mitdb(target_dir="dataset/mitdb"):
    """
    Downloads the MIT-BIH Arrhythmia Database from PhysioNet.
    """
    logger.info("Starting MIT-BIH Arrhythmia Database download...")
    
    # Ensure directory exists
    os.makedirs(target_dir, exist_ok=True)
    
    try:
        # Check if already downloaded (e.g. check if a few records exist)
        expected_records = 48
        existing_hea = [f for f in os.listdir(target_dir) if f.endswith(".hea")]
        existing_dat = [f for f in os.listdir(target_dir) if f.endswith(".dat")]
        existing_atr = [f for f in os.listdir(target_dir) if f.endswith(".atr")]
        
        if len(existing_hea) >= expected_records and len(existing_dat) >= expected_records:
            logger.info(f"MIT-BIH Database already downloaded in {target_dir} ({len(existing_hea)} records found). Skipping download.")
            return True
            
        logger.info("Downloading database using wfdb.dl_database...")
        # Download database (downloads header, signal data, and annotations)
        wfdb.dl_database("mitdb", dl_dir=target_dir)
        logger.info("Download completed successfully!")
        return True
    except Exception as e:
        logger.error(f"Error downloading MIT-BIH database: {e}")
        logger.info("Retrying download for core files individually...")
        # Fallback method: download core records list if dl_database fails
        try:
            records = [
                100, 101, 102, 103, 104, 105, 106, 107, 108, 109,
                111, 112, 113, 114, 115, 116, 117, 118, 119, 121,
                122, 123, 124, 200, 201, 202, 203, 205, 207, 208,
                209, 210, 212, 213, 214, 215, 217, 219, 220, 221,
                222, 223, 228, 230, 231, 232, 233, 234
            ]
            for r in records:
                r_str = str(r)
                for ext in ["dat", "hea", "atr"]:
                    file_name = f"{r_str}.{ext}"
                    file_path = os.path.join(target_dir, file_name)
                    if not os.path.exists(file_path):
                        logger.info(f"Downloading {file_name}...")
                        # Download single file from PhysioNet
                        url = f"https://physionet.org/files/mitdb/1.0.0/{file_name}"
                        import requests
                        r_req = requests.get(url, stream=True)
                        if r_req.status_code == 200:
                            with open(file_path, "wb") as f:
                                for chunk in r_req.iter_content(chunk_size=1024):
                                    if chunk:
                                        f.write(chunk)
                        else:
                            logger.error(f"Failed to download {file_name} (status code: {r_req.status_code})")
            logger.info("Fallback download completed!")
            return True
        except Exception as fallback_err:
            logger.error(f"Fallback download failed: {fallback_err}")
            return False

if __name__ == "__main__":
    download_mitdb()

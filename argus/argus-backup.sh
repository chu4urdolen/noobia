echo "Backing up /home/todor/argus → /mnt/nvme/backups/argus"
sudo rsync -aAXHv --delete /home/todor/argus/ /mnt/nvme/backups/argus/

echo "Backing up /home/todor/rose → /mnt/nvme/backups/rose"
sudo rsync -aAXHv --delete /home/todor/rose/  /mnt/nvme/backups/rose/

echo "Backing up /mnt/nvme/argus → /mnt/nvme/backups/nvme_argus"
sudo rsync -aAXHv --delete /mnt/nvme/argus/   /mnt/nvme/backups/nvme_argus/

echo "Backup complete."

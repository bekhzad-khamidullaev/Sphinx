from celery import shared_task
from .models import NetPingDevice as Device
import asyncio
import logging
import time
from ping3 import ping
from asgiref.sync import sync_to_async

@shared_task
def update_device_status():

    @sync_to_async
    def save_device(self, device):
        device.save()

    async def update_device_status(self, ip_address):
        try:
            if ip_address is None:
                return

            start_time = time.time()

            host_alive = ping(ip_address, unit='ms', size=32, timeout=2)

            elapsed_time = time.time() - start_time

            device = await sync_to_async(Device.objects.filter(ip_address=ip_address).first)()

            if device is None:
                status = False
                logger.info(f"Device with IP {ip_address} not found.")
            else:
                status = bool(host_alive)
                logger.info(f"Device {ip_address} is {'alive' if status else 'down'}")
                device.status = status
                await self.save_device(device)

        except Exception as e:
            logger.error(f"Error updating device status for {ip_address}: {e}")

    async def handle_async(self, *args, **options):
        total_start_time = time.time()
        devices_per_batch = 5

        try:
            while True:
                devices_count = await sync_to_async(Device.objects.count)()

                for offset in range(0, devices_count, devices_per_batch):
                    ip_addresses = await sync_to_async(list)(
                        Device.objects.values_list('ip_address', flat=True)[offset:offset + devices_per_batch]
                    )

                    batch_start_time = time.time()
                    logger.info(f"Processing batch with {len(ip_addresses)} devices.")

                    tasks = [self.update_device_status(ip) for ip in ip_addresses]
                    await asyncio.gather(*tasks)

                    batch_elapsed_time = time.time() - batch_start_time
                    logger.info(f"Batch processed in {batch_elapsed_time:.2f} seconds")

                # Introduce a delay between iterations
                await asyncio.sleep(360)  # Adjust the delay as needed (e.g., 60 seconds)

                total_elapsed_time = time.time() - total_start_time
                logger.info(f"Total elapsed time: {total_elapsed_time:.2f} seconds")

        except KeyboardInterrupt:
            logger.info("Received KeyboardInterrupt. Stopping the update process.")

    def handle(self, *args, **options):
        loop = asyncio.get_event_loop()
        try:
            loop.run_until_complete(self.handle_async(*args, **options))
        except KeyboardInterrupt:
            # Allow the program to be terminated gracefully with Ctrl+C
            pass


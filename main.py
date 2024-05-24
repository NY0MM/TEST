import json
import logging
import pyshorteners
import urllib.parse
from configparser import ConfigParser
from datetime import datetime, timedelta
from re import match
from time import time, sleep  # noqa
from typing import Dict, List, Union
from params_file import params
import pytz
import requests
from discord_webhook import DiscordWebhook



CONFIG_FILE_NAME = "config.ini"

def configure_logging() -> None:
    """Set up logging."""
    # Set up the console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.DEBUG)
    console_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)

    # Set up the file handler
    file_handler = logging.FileHandler("keepa_notifier.log", mode="a")
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter("%(asctime)s - %(levelname)s - %(message)s")
    file_handler.setFormatter(file_formatter)

    # Configure the logger
    logger = logging.getLogger()
    logger.setLevel(logging.DEBUG)
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)


class KeepaDiscordNotifier(object):
    """A class to fetch product data from the Keepa API and send notifications to a Discord channel."""

    def __init__(self, api_key: str, discord_webhook_url: str):
        """
        Initializes a KeepaDiscordNotifier instance with the given Keepa API key and Discord webhook URL.

        :param api_key: The Keepa API key
        :param discord_webhook_url: The Discord webhook URL
        """
        self.api_key = api_key
        self.discord_webhook_url = discord_webhook_url
        self.notified_asins = []
        self.credentials_valid = self.check_credentials(k=self.api_key, d=self.discord_webhook_url)

        logging.debug(
            f"{type(self).__name__} initialized with key: {self.api_key}, URL: {self.discord_webhook_url}"
        )

    def update_asin_list(self) -> None:
        """
        Update the 'asins.txt' file with the ASINs stored in the `notified_asins` attribute.

        This method appends each ASIN in the `notified_asins` list to the 'asins.txt' file and
        clears the `notified_asins` list afterward.
        """
        with open("asins.txt", "a") as f:
            for asin in self.notified_asins:
                f.write(f"{asin}\n")
        self.notified_asins = []

    @staticmethod
    def get_asin_list() -> List[str]:
        """
        Read the ASINs from the 'asins.txt' file and return them as a list of strings.

        :return: A list of ASIN strings read from the 'asins.txt' file.
        """
        asins = []
        with open("asins.txt", "r") as f:
            for line in f:
                asins.append(line.strip())
        return asins

    @classmethod
    def check_credentials(cls, *, k: str, d: str) -> bool:
        """
        Checks if the given Keepa API key and Discord webhook URL have valid formats.

        This function uses regular expressions to validate the format of the Keepa API key
        and Discord webhook URL. It does not guarantee that the credentials will work with
        the respective services, but it provides a basic estimation.

        :param k: The Keepa API key to check
        :param d: The Discord webhook URL to check
        :return: True if both credentials have valid formats, False otherwise
        """
        valid = True

        # Check Keepa API key (assuming it has 10 alphanumeric characters)
        if not match(r"^[a-zA-Z0-9]{64}$", k):
            logging.error("Keepa API key may be invalid")
            valid = False

        # Check Discord webhook URL
        discord_url_pattern = r"^https://discord(?:app)?\.com/api/webhooks/\d+/[a-zA-Z0-9_-]+$"
        if not match(discord_url_pattern, d):
            logging.error("Discord webhook URL may be invalid")
            valid = False

        return valid

    def build_keepa_query_url(
            self, parameters: Dict[str, Union[str, int, List]]
    ) -> str:
        """
        Builds the Keepa API query URL using the given parameters.

        :param parameters: A dictionary of parameters for the Keepa API query
        :return: The Keepa API query URL
        """
        query_json = json.dumps(parameters)
        url_encoded_query_json = urllib.parse.quote(query_json)
        url = f"https://api.keepa.com/query?key={self.api_key}&domain=2&selection={url_encoded_query_json}"
        # print(url)
        logging.debug(f"Keepa API query URL built: {url}")
        return url


    def fetch_keepa_data(self,asin):

    # Discord webhook URL
        # Make API request to retrieve product information
        response = requests.get(f"https://api.keepa.com/product?key={self.api_key}&domain=2&asin={asin}&stats=180&buybox=1&history=1")

       # Check if the request was successful
        if response.status_code == 200:
         product_data = response.json()
         return product_data
        else:
          logging.debug(f"Keepa Token Low wait 10 min : status_code{response.status_code}")
          sleep(500)  # Sleep for 5 min
          return self.fetch_keepa_data(asin)



    def find_object_by_asin(self, variations, asin):
        if variations is not None:
            found_object = next((variation for variation in variations if variation['asin'] == asin), None)
            if found_object:
                dimensions_values = [f"{attribute['dimension']}: {attribute['value']}" for attribute in found_object['attributes']]
                return ", ".join(dimensions_values)
        return ''

    def find_total_variant(self, variation_csv):
        if variation_csv:
            values_array = variation_csv.split(',')
            count = len(values_array)
            if count > 0:
                return count
        return 1

    def parse_images_csv(self, images_csv):
      if not images_csv:
          return []

      base_url = "https://m.media-amazon.com/images/I/"
      image_filenames = [image_filename.strip() for image_filename in images_csv.split(',')]

      if image_filenames:
          first_image_url = base_url + image_filenames[0]
          return first_image_url
      else:
          return None 


    def random_yellow_or_blue(self,availabilityAmazon):
      # Define ranges for yellow (high red and green, low blue)
      yellow_color = 16705372

      # Define ranges for blue (high blue, low red and green)
      blue_color = 3447003

      if(availabilityAmazon == 1):
         return blue_color
      else:
         # Select a random color
          return yellow_color  

    def send_discord_notification(self, product: Dict[str, str]) -> None:
        """
        Sends a notification to the Discord channel for the provided product.

        :param product: A dictionary containing product details
        """
        asin = product  # noqa
        amazon_url = f"https://www.amazon.co.uk/dp/{asin}/ref=pd_ci_mcx_mh_mcx_views_4?pd_rd_w=DuqJH&content-id=amzn1.sym.225b4624-972d-4629-9040-f1bf9923dd95%3Aamzn1.symc.40e6a10e-cbc4-4fa5-81e3-4435ff64d03b&pf_rd_p=225b4624-972d-4629-9040-f1bf9923dd95&tag=amzdeals0a8a-20&pf_rd_r=HQ8J9WPF7RF8TYFS5WHH&pd_rd_wg=K1vJJ&pd_rd_r=43a8bdb0-ad87-42fa-93cf-6bc39ecee2a8&pd_rd_i={asin}&th=1&psc=1"

        keepa_url = f"https://keepa.com/#!product/1-{asin}"
        image_url = f"https://api.keepa.com/graphimage?key={self.api_key}&domain=2&asin={asin}&amazon=1&new=1&bb=1&salesrank=1&range=30"


       # Create an instance of the Shortener class

       # Shorten the URL
        # short_url = shortener.tinyurl.short(image_url)
        short_url = image_url


        keepa_response = self.fetch_keepa_data(asin)
         # Extract product price and BSR data
        product_title = keepa_response["products"][0]["title"]


        # print(keepa_response["products"][0])
        bsr_data = keepa_response["products"][0]["stats"]["current"][3]
        BUY_BOX_SHIPPING = keepa_response["products"][0]["stats"]["current"][18]/100
        BUY_BOX_SHIPPING_AVG_30 = keepa_response["products"][0]["stats"]["avg90"][18]/100
        totalSellerCount = keepa_response["products"][0]["stats"]["totalOfferCount"]

        current_bb_price = BUY_BOX_SHIPPING
        bb_30day_price = BUY_BOX_SHIPPING_AVG_30
        percentage_of_30day_price = (bb_30day_price / 100) * 15
        amazon_fee = 8
        estimated_fees = percentage_of_30day_price + amazon_fee
        estimated_profit = bb_30day_price - current_bb_price - percentage_of_30day_price - amazon_fee

        #More Accurate Profit Calculation
        fba_fees = keepa_response["products"][0]["fbaFees"]
        if fba_fees and "pickAndPackFee" in fba_fees:
             fbaFees = fba_fees['pickAndPackFee'] / 100
        else:
              fbaFees = 0

        referralFeePercent = keepa_response["products"][0]["referralFeePercent"] if "referralFeePercent" in keepa_response["products"][0] else 15
        referralFee = (referralFeePercent*bb_30day_price)/100
        totalAmzFee = fbaFees + referralFee
        shippingCost = 2
        sellPrice = bb_30day_price
        buyCost = current_bb_price

        profit = sellPrice - totalAmzFee  - buyCost

        margin = (profit/sellPrice)*100

        if buyCost >0 :
          roi = (profit/buyCost)*100
        else:
          roi = 0


        availabilityAmazon = keepa_response["products"][0]["availabilityAmazon"]
        monthlySold = keepa_response["products"][0].get("monthlySold", '')

         # random_color
        random_color = self.random_yellow_or_blue(availabilityAmazon)

        isAmzn = "No"

        if availabilityAmazon == 0:
              isAmzn = 'Yes'

        variant_product = keepa_response["products"][0]
        # logging.debug(f"variations: {variant_product['variations']}")
        variation_attributes = f"Variant: {self.find_total_variant(variant_product['variationCSV'])} " + self.find_object_by_asin(variant_product['variations'], variant_product['asin']) if 'variations' in variant_product else 'Variant: 1'

        thumbnailimg_url = self.parse_images_csv(variant_product['imagesCSV'])

        # Creating the embedded message
        embed = {
            "title": product_title,
            "url": amazon_url,
            "description":
                    f"` ▸ ` **ASIN**: {asin}\n"
                    f"` ▸ ` **Monthly Sold**: {monthlySold}\n"
                    f"` ▸ ` **Current Price**: £{round(current_bb_price, 2)}\n"
                    f"` ▸ ` **Est Sell Price**: £{round(bb_30day_price, 2)}\n"
                    f"` ▸ ` **Est Amz Fees**: £{round(totalAmzFee, 2)}\n"
                    f"` ▸ ` **Est Profit**: £{round(profit, 2)}\n"
                    f"` ▸ ` **Est Margin**: {round(margin, 2)}%\n"
                    f"` ▸ ` **Est ROI**: {round(roi, 2)}%\n\n"
                    f"` ▸ ` **BSR**: {bsr_data}\n"
                    f"` ▸ ` **Total Seller Count**: {totalSellerCount}\n"
                    f"` ▸ ` **Variation**: {variation_attributes}\n"
                    f"` ▸ ` **Is Amz Selling**: {isAmzn}\n\n"
                    f"` ▸ ` **Explore on ** [Keepa]({keepa_url}) | [Amazon]({amazon_url})",
            "color": random_color  ,#RANDOM 702963
            "image": {"url": f"{short_url}"}
        }

       # Set the thumbnail image
        embed["thumbnail"] = {"url": thumbnailimg_url}
        webhook = DiscordWebhook(
            url=self.discord_webhook_url,
            username= 'AmzLead',
            embeds=[embed]
        )
        # if estimated_profit > 0:
        webhook.execute()
        logging.info(f"Discord notification sent for ASIN: {asin}")


            # Sleep for 3 seconds
            # sleep(3)


    def fetch_products(
            self, parameters: Dict[str, Union[str, int, List]]
    ) -> List[Dict[str, str]]:
        """
        Fetches products from the Keepa API using the given parameters.

        :param parameters: A dictionary of parameters for the Keepa API query
        :return: A list of dictionaries containing product details
        """
        url = self.build_keepa_query_url(parameters)
        headers = {"User-Agent": "Python Keepa API Script"}

        try:
            response = requests.get(url, headers=headers)
            if not response.ok:
                logging.error(f"Response not OK ({response.status_code})")
                logging.debug(f"Error details: {response.json()}")

            response_data = response.json()
            products = response_data.get("asinList", [])
             #logging.debug(f"Fetched {result} products from Keepa API")
            logging.debug(f"Fetched {len(products)} products from Keepa API")
            return products
        except requests.RequestException as e:
            logging.error(f"Error while querying Keepa API: {e}")
            return []
        except Exception as e:
            logging.error(f"An unexpected error occurred: {e}")
            return []

    def notify_products(self, parameters: Dict[str, Union[str, int, List]]) -> None:
        """
        Fetches products and sends notifications for each product.

        :param parameters: A dictionary of parameters for the Keepa API query
        """

        # Initialize an empty list to store the responses
        total_products = []

        # Iterate over the 'params' array
        for parameters in params:
            response = self.fetch_products(parameters)
            logging.debug(f"parameters: {parameters}")
            logging.debug(f"response: {response}")
            # products.append(response)
            total_products += response


        logging.debug(f"total products: {total_products}")

        # Convert the 'products' list to a set to remove duplicates
        unique_products_set = set(total_products)

        # Convert the set back to a list if you need it as a list
        products = list(unique_products_set)
        logging.debug(f"total unique_products_list : {products}")

        if products:
            for product in products:
                # If the product's ASIN is not in the file, send a notification
                if product not in self.get_asin_list():
                    self.send_discord_notification(product)
                    self.notified_asins.append(product)
                    self.update_asin_list()
        else:
            logging.info("No products found in the response")
        logging.debug("Product notification process completed")


if __name__ == "__main__":
    configure_logging()

    config = ConfigParser()
    config.read(CONFIG_FILE_NAME)

    API_KEY = config.get("KEEPADISCORD", "API_KEY")
    DISCORD_WEBHOOK_URL = config.get("KEEPADISCORD", "DISCORD_WEBHOOK_URL")

    if not all((API_KEY, DISCORD_WEBHOOK_URL)):
        raise Exception(
            f"Arguments missing values: {', '.join(a for a in (API_KEY, DISCORD_WEBHOOK_URL) if not a)}"
        )

    notifier = KeepaDiscordNotifier(API_KEY, DISCORD_WEBHOOK_URL)
    while True:
        logging.debug(f"Start Track")
        notifier.notify_products(params)
        sleep(180)  # Sleep for .05 hours

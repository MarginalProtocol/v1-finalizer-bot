# v1-finalizer-bot

Finalizer bot that finalizes [Marginal v1 liquidity bootstrapping pools](https://github.com/MarginalProtocol/v1-lbp), minting liquidity on Uniswap v3 and then Marginal v1.

## Installation

The repo uses [ApeWorX](https://github.com/apeworx/ape) and [Silverback](https://github.com/apeworx/silverback) for development.

Set up a virtual environment

```sh
python -m venv .venv
source .venv/bin/activate
```

Install requirements and Ape plugins

```sh
pip install -r requirements.txt
ape plugins install .
```

## Usage

Include the environment variables for the address of the [`MarginalV1LBSupplier`](https://github.com/MarginalProtocol/v1-lbp/blob/main/contracts/MarginalV1LBSupplier.sol),
the address of the [`MarginalV1Factory`](https://github.com/MarginalProtocol/v1-core/blob/main/contracts/MarginalV1Factory.sol),
and the address of the [`MarginalV1LBPool`](https://github.com/MarginalProtocol/v1-lbp/blob/main/contracts/MarginalV1LBPool.sol) you wish to watch

```sh
export CONTRACT_ADDRESS_MARGV1LB_SUPPLIER=<address of marginal v1lb supplier contract on network>
export CONTRACT_ADDRESS_MARGV1LB_POOL=<address of marginal v1lb pool contract on network>
export CONTRACT_ADDRESS_MARGV1_FACTORY=<address of marginal v1 factory contract on network>
```

Then run silverback


```sh
silverback run "main:app" --network :mainnet:alchemy --account acct-name
```
